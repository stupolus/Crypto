"""RiskEngine: размер позиции от риска + circuit breakers.

Приоритет №1 — сохранность капитала. Все числа берутся из RiskConfig
(зеркало risk-profile.md), не хардкодятся.

Поток:
- `compute_sizing` — чистый расчёт размера + проверки плеча/стопа/ликвидации.
- `RiskState` — изменяемое состояние счёта (pnl за период, серия убытков,
  пик эквити, открытые позиции, частота сделок).
- `evaluate_entry` — все гейты входа по порядку; возвращает Approval|Rejection.
- `register_open` / `register_close` — обновление состояния и срабатывание
  circuit breakers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from exchanges.models import OrderSide
from risk.config import RiskConfig


@dataclass(frozen=True)
class Sizing:
    risk_amount: Decimal
    notional: Decimal
    quantity: Decimal
    effective_leverage: Decimal
    liquidation_price: Decimal
    stop_distance_pct: Decimal


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str | None = None
    sizing: Sizing | None = None

    @classmethod
    def approve(cls, sizing: Sizing) -> RiskDecision:
        return cls(approved=True, sizing=sizing)

    @classmethod
    def reject(cls, reason: str) -> RiskDecision:
        return cls(approved=False, reason=reason)


@dataclass(frozen=True)
class EntryContext:
    symbol: str
    asset_class: str
    side: OrderSide
    equity: Decimal
    entry: Decimal
    stop: Decimal
    risk_pct: Decimal
    expected_tp_pct: Decimal
    expected_cost_pct: Decimal
    spread: Decimal
    spread_median: Decimal
    now_ts: float


def _liquidation_price(entry: Decimal, side: OrderSide, lev_cap: Decimal, mmr: Decimal) -> Decimal:
    """Пессимистичная оценка цены ликвидации (isolated, linear), L = потолок плеча."""
    inv = Decimal(1) / lev_cap
    if side is OrderSide.BUY:
        return entry * (Decimal(1) - inv + mmr)
    return entry * (Decimal(1) + inv - mmr)


def compute_sizing(
    cfg: RiskConfig,
    equity: Decimal,
    entry: Decimal,
    stop: Decimal,
    side: OrderSide,
    risk_pct: Decimal,
) -> RiskDecision:
    if equity <= 0 or entry <= 0 or stop <= 0:
        return RiskDecision.reject("invalid_inputs")
    if side is OrderSide.BUY and stop >= entry:
        return RiskDecision.reject("stop_wrong_side")
    if side is OrderSide.SELL and stop <= entry:
        return RiskDecision.reject("stop_wrong_side")

    stop_distance_pct = abs(entry - stop) / entry
    if stop_distance_pct < cfg.min_stop_distance_pct:
        return RiskDecision.reject("stop_too_tight")

    risk_amount = equity * risk_pct
    notional = risk_amount / stop_distance_pct
    quantity = notional / entry
    effective_leverage = notional / equity
    if effective_leverage > cfg.max_effective_leverage:
        return RiskDecision.reject("leverage_exceeded")

    liq = _liquidation_price(entry, side, cfg.max_effective_leverage, cfg.maintenance_margin_rate)
    # стоп должен срабатывать раньше ликвидации и с буфером
    entry_to_stop = abs(entry - stop)
    stop_to_liq = abs(stop - liq)
    liq_beyond_stop = liq < stop if side is OrderSide.BUY else liq > stop
    if not liq_beyond_stop or stop_to_liq < cfg.liq_buffer_min_frac * entry_to_stop:
        return RiskDecision.reject("liquidation_buffer")

    return RiskDecision.approve(
        Sizing(
            risk_amount=risk_amount,
            notional=notional,
            quantity=quantity,
            effective_leverage=effective_leverage,
            liquidation_price=liq,
            stop_distance_pct=stop_distance_pct,
        )
    )


@dataclass
class RiskState:
    """Изменяемое состояние счёта для circuit breakers."""

    active_capital: Decimal
    equity_peak: Decimal
    day: date
    iso_week: tuple[int, int]
    month: tuple[int, int]
    day_pnl: Decimal = Decimal(0)
    week_pnl: Decimal = Decimal(0)
    month_pnl: Decimal = Decimal(0)
    consecutive_losses: int = 0
    killed: bool = False
    halted_days: set[date] = field(default_factory=set)
    open_positions: list[tuple[str, str]] = field(default_factory=list)
    trades_today_total: int = 0
    trades_today_by_symbol: dict[str, int] = field(default_factory=dict)
    last_trade_ts_by_symbol: dict[str, float] = field(default_factory=dict)

    @classmethod
    def new(cls, active_capital: Decimal, now: date) -> RiskState:
        return cls(
            active_capital=active_capital,
            equity_peak=active_capital,
            day=now,
            iso_week=(now.isocalendar().year, now.isocalendar().week),
            month=(now.year, now.month),
        )

    def roll_period(self, now: date) -> None:
        if now != self.day:
            self.day = now
            self.day_pnl = Decimal(0)
            self.trades_today_total = 0
            self.trades_today_by_symbol = {}
        wk = (now.isocalendar().year, now.isocalendar().week)
        if wk != self.iso_week:
            self.iso_week = wk
            self.week_pnl = Decimal(0)
        mo = (now.year, now.month)
        if mo != self.month:
            self.month = mo
            self.month_pnl = Decimal(0)

    def update_equity(self, equity: Decimal, cfg: RiskConfig) -> None:
        if equity > self.equity_peak:
            self.equity_peak = equity
        if self.equity_peak > 0:
            drawdown = (equity - self.equity_peak) / self.equity_peak
            if drawdown <= cfg.global_killswitch_dd_pct:
                self.killed = True


class RiskEngine:
    def __init__(self, cfg: RiskConfig) -> None:
        self._cfg = cfg

    def evaluate_entry(self, state: RiskState, ctx: EntryContext) -> RiskDecision:
        cfg = self._cfg
        if state.killed:
            return RiskDecision.reject("killswitch")
        if state.day in state.halted_days:
            return RiskDecision.reject("halted")
        cap = state.active_capital
        if cap > 0:
            if state.day_pnl / cap <= cfg.daily_stop_pct:
                return RiskDecision.reject("daily_stop")
            if state.week_pnl / cap <= cfg.weekly_stop_pct:
                return RiskDecision.reject("weekly_stop")
            if state.month_pnl / cap <= cfg.monthly_stop_pct:
                return RiskDecision.reject("monthly_stop")
        if state.consecutive_losses >= cfg.max_consecutive_losses:
            return RiskDecision.reject("consecutive_losses")

        if len(state.open_positions) >= cfg.max_positions_total:
            return RiskDecision.reject("max_positions_total")
        in_class = sum(1 for _, c in state.open_positions if c == ctx.asset_class)
        if in_class >= cfg.max_positions_per_class:
            return RiskDecision.reject("max_positions_per_class")
        in_symbol = sum(1 for s, _ in state.open_positions if s == ctx.symbol)
        if in_symbol >= cfg.max_positions_per_symbol:
            return RiskDecision.reject("max_positions_per_symbol")

        if state.trades_today_total >= cfg.max_trades_per_day:
            return RiskDecision.reject("max_trades_per_day")
        if state.trades_today_by_symbol.get(ctx.symbol, 0) >= cfg.max_trades_per_symbol_per_day:
            return RiskDecision.reject("max_trades_per_symbol")
        last = state.last_trade_ts_by_symbol.get(ctx.symbol)
        if last is not None and ctx.now_ts - last < cfg.min_seconds_between_trades_same_symbol:
            return RiskDecision.reject("trade_interval")

        if ctx.spread_median > 0 and ctx.spread > cfg.spread_max_mult * ctx.spread_median:
            return RiskDecision.reject("spread_too_wide")
        if ctx.expected_tp_pct < cfg.cost_edge_min_ratio * ctx.expected_cost_pct:
            return RiskDecision.reject("cost_edge")

        return compute_sizing(cfg, ctx.equity, ctx.entry, ctx.stop, ctx.side, ctx.risk_pct)

    def register_open(self, state: RiskState, symbol: str, asset_class: str, now_ts: float) -> None:
        state.open_positions.append((symbol, asset_class))
        state.trades_today_total += 1
        state.trades_today_by_symbol[symbol] = state.trades_today_by_symbol.get(symbol, 0) + 1
        state.last_trade_ts_by_symbol[symbol] = now_ts

    def register_close(
        self, state: RiskState, symbol: str, pnl: Decimal, equity_after: Decimal
    ) -> None:
        cfg = self._cfg
        for i, (s, _) in enumerate(state.open_positions):
            if s == symbol:
                del state.open_positions[i]
                break
        state.day_pnl += pnl
        state.week_pnl += pnl
        state.month_pnl += pnl
        state.consecutive_losses = state.consecutive_losses + 1 if pnl < 0 else 0
        state.update_equity(equity_after, cfg)

        cap = state.active_capital
        if cap > 0 and (
            state.day_pnl / cap <= cfg.daily_stop_pct
            or state.consecutive_losses >= cfg.max_consecutive_losses
        ):
            state.halted_days.add(state.day)
