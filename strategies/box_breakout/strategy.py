"""box_breakout (#008, план 50): пробой консолидационного бокса с
volume-bias. Только klines → backtest/WF без блокеров данных.

Реализует ``Strategy`` protocol (backtest + live одинаково).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum

from adapters.bingx.models import Kline
from adapters.bingx.private_models import OrderRequest, OrderSide
from core.backtest import FillEvent, StrategyContext
from core.risk import RiskApproval, RiskEngine, RiskInputs, RiskRejection, Side
from core.signals import atr
from strategies.box_breakout.config import BoxBreakoutConfig

logger = logging.getLogger(__name__)

_HUNDRED = Decimal("100")
_DAY_MS = 86_400_000


class _State(StrEnum):
    FLAT = "FLAT"
    PENDING = "PENDING"
    OPEN = "OPEN"


class BoxBreakoutStrategy:
    """Пробой узкого бокса в сторону нетто-объёма (план 50)."""

    def __init__(self, config: BoxBreakoutConfig, risk_engine: RiskEngine) -> None:
        self._cfg = config
        self._risk = risk_engine
        self._state = _State.FLAT
        self._pending_coid: str | None = None
        self._day_pnl = Decimal("0")
        self._day_trades_count = 0
        self._consecutive_losses = 0
        self._current_utc_day: int | None = None

    def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None:
        candle = ctx.current_candle
        self._roll_day_if_needed(candle.open_time_ms)

        if ctx.open_position is not None:
            self._state = _State.OPEN
            return None
        if self._state == _State.PENDING:
            return None
        self._state = _State.FLAT

        min_history = max(self._cfg.box_n, self._cfg.atr_window + 1, self._cfg.vol_sma_window) + 1
        if len(ctx.history) < min_history:
            return None

        closed = ctx.history[:-1]
        box = closed[-self._cfg.box_n :]
        hi = max(c.high for c in box)
        lo = min(c.low for c in box)
        mid = (hi + lo) / 2
        if mid <= 0:
            return None
        width_pct = (hi - lo) / mid * _HUNDRED
        if width_pct > Decimal(str(self._cfg.box_max_width_pct)):
            return None  # не консолидация

        bias = sum((Decimal(1) if c.close > c.open else Decimal(-1)) * c.volume for c in box)
        long_trig = candle.close > hi and bias > 0
        short_trig = candle.close < lo and bias < 0
        if self._cfg.direction_bias == "long_only":
            short_trig = False
        elif self._cfg.direction_bias == "short_only":
            long_trig = False
        if not (long_trig or short_trig):
            return None

        avg_vol = sum(c.volume for c in box) / Decimal(len(box))
        if candle.volume < avg_vol * Decimal(str(self._cfg.breakout_vol_mult)):
            return None  # слабый пробой

        side: OrderSide = "BUY" if long_trig else "SELL"
        entry = candle.close
        stop = self._compute_stop(entry, side, closed)
        tp = self._compute_tp(entry, stop, side)
        risk_side = Side.LONG if side == "BUY" else Side.SHORT

        decision = self._risk.evaluate(
            RiskInputs(
                equity=ctx.equity,
                side=risk_side,
                entry_price=entry,
                stop_price=stop,
                take_profit_price=tp,
                tier=self._cfg.risk_tier,
                day_pnl=self._day_pnl,
                day_trades_count=self._day_trades_count,
                consecutive_losses=self._consecutive_losses,
            )
        )
        if isinstance(decision, RiskRejection):
            logger.info("box_breakout rejected by RiskEngine: %s", decision.code)
            return None
        assert isinstance(decision, RiskApproval)

        coid = uuid.uuid4().hex[:32]
        self._pending_coid = coid
        self._state = _State.PENDING
        return OrderRequest(
            symbol=self._cfg.symbol,
            side=side,
            order_type="MARKET",
            quantity=decision.quantity,
            attached_stop_loss=stop,
            attached_take_profit=tp,
            client_order_id=coid,
        )

    def on_fill(self, fill: FillEvent) -> None:
        if fill.reason == "ENTRY":
            self._state = _State.OPEN
            return
        self._day_trades_count += 1
        if fill.reason == "STOP_LOSS":
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        self._state = _State.FLAT
        self._pending_coid = None

    # ── helpers ──────────────────────────────────────────────────────────

    def _compute_stop(self, entry: Decimal, side: OrderSide, closed: Sequence[Kline]) -> Decimal:
        a = atr(closed, self._cfg.atr_window)
        atr_dist = a * Decimal(str(self._cfg.atr_sl_mult))
        min_dist = entry * Decimal(str(self._cfg.stop_min_pct)) / _HUNDRED
        dist = max(atr_dist, min_dist)
        return entry - dist if side == "BUY" else entry + dist

    def _compute_tp(self, entry: Decimal, stop: Decimal, side: OrderSide) -> Decimal:
        dist = abs(entry - stop)
        r = Decimal(str(self._cfg.tp_r))
        return entry + r * dist if side == "BUY" else entry - r * dist

    def _roll_day_if_needed(self, ts_ms: int) -> None:
        day = ts_ms // _DAY_MS
        if self._current_utc_day is None:
            self._current_utc_day = day
            return
        if day != self._current_utc_day:
            self._current_utc_day = day
            self._day_pnl = Decimal("0")
            self._day_trades_count = 0
            self._consecutive_losses = 0
