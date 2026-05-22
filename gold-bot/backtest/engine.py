"""Event-driven бэктестер (одна позиция за раз, v1).

Правила (CLAUDE.md §8):
- Стратегия видит history[:i+1], не видит будущее.
- MARKET-fill по open(c+1).
- Стоп/тейк проверяются внутри бара по high/low; если в одном баре задеты оба —
  консервативно считаем срабатывание стопа.
- Издержки на вход и выход.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backtest.costs import CostModel
from backtest.strategy import Signal, Strategy
from exchanges.models import OHLCV, OrderSide
from risk.config import RiskConfig
from risk.engine import compute_sizing


@dataclass(frozen=True)
class Trade:
    entry_ts: int
    exit_ts: int
    side: OrderSide
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    exit_reason: str  # "stop" | "tp" | "eod"


@dataclass(frozen=True)
class BacktestResult:
    trades: list[Trade]
    equity_curve: list[Decimal]  # эквити после каждой закрытой сделки, [0] = старт


@dataclass
class _OpenPosition:
    side: OrderSide
    entry_ts: int
    entry_price: Decimal
    quantity: Decimal
    stop: Decimal
    take_profit: Decimal
    entry_cost: Decimal


def _exit_level(candle: OHLCV, pos: _OpenPosition) -> tuple[Decimal, str] | None:
    """Сработал ли стоп/тейк внутри бара. Консервативно: при обоих — стоп."""
    if pos.side is OrderSide.BUY:
        if candle.low <= pos.stop:
            return pos.stop, "stop"
        if candle.high >= pos.take_profit:
            return pos.take_profit, "tp"
    else:
        if candle.high >= pos.stop:
            return pos.stop, "stop"
        if candle.low <= pos.take_profit:
            return pos.take_profit, "tp"
    return None


class BacktestEngine:
    def __init__(
        self,
        strategy: Strategy,
        cost_model: CostModel,
        risk_cfg: RiskConfig,
        equity0: Decimal,
    ) -> None:
        self._strategy = strategy
        self._costs = cost_model
        self._cfg = risk_cfg
        self._equity0 = equity0

    def run(self, candles: list[OHLCV]) -> BacktestResult:
        equity = self._equity0
        trades: list[Trade] = []
        equity_curve: list[Decimal] = [equity]
        pos: _OpenPosition | None = None

        for i in range(len(candles) - 1):
            if pos is None:
                signal = self._strategy.on_candle(candles[: i + 1])
                if signal is not None:
                    pos = self._try_open(signal, candles[i + 1], equity)
                continue

            exit_hit = _exit_level(candles[i], pos)
            if exit_hit is not None:
                exit_price, reason = exit_hit
                trade, equity = self._close(pos, candles[i].timestamp, exit_price, reason, equity)
                trades.append(trade)
                equity_curve.append(equity)
                pos = None

        return BacktestResult(trades=trades, equity_curve=equity_curve)

    def _try_open(
        self, signal: Signal, next_candle: OHLCV, equity: Decimal
    ) -> _OpenPosition | None:
        entry = next_candle.open
        decision = compute_sizing(
            self._cfg, equity, entry, signal.stop, signal.side, signal.risk_pct
        )
        if not decision.approved or decision.sizing is None:
            return None
        qty = decision.sizing.quantity
        entry_cost = self._costs.leg_cost(qty * entry)
        return _OpenPosition(
            side=signal.side,
            entry_ts=next_candle.timestamp,
            entry_price=entry,
            quantity=qty,
            stop=signal.stop,
            take_profit=signal.take_profit,
            entry_cost=entry_cost,
        )

    def _close(
        self, pos: _OpenPosition, exit_ts: int, exit_price: Decimal, reason: str, equity: Decimal
    ) -> tuple[Trade, Decimal]:
        direction = Decimal(1) if pos.side is OrderSide.BUY else Decimal(-1)
        gross = (exit_price - pos.entry_price) * pos.quantity * direction
        exit_cost = self._costs.leg_cost(pos.quantity * exit_price)
        total_costs = pos.entry_cost + exit_cost
        net = gross - total_costs
        new_equity = equity + net
        trade = Trade(
            entry_ts=pos.entry_ts,
            exit_ts=exit_ts,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            quantity=pos.quantity,
            gross_pnl=gross,
            costs=total_costs,
            net_pnl=net,
            exit_reason=reason,
        )
        return trade, new_equity
