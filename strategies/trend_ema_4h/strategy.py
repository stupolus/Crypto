"""Trend following EMA cross 4h стратегия.

Логика: ждём `EMA(20) > EMA(50)` (или `<` для SHORT) с достаточным
spread, затем ждём pullback к EMA(20) и close в сторону тренда → BUY.
SL = ATR × 1.5, TP1 = 1.5R.

Спецификация: plans/15-trend-following-4h.md.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from decimal import Decimal

from adapters.bingx.models import Kline
from adapters.bingx.private_models import OrderRequest, OrderSide
from core.backtest import FillEvent, StrategyContext
from core.risk import RiskApproval, RiskEngine, RiskInputs, RiskRejection, Side
from core.signals import atr, ema
from strategies.trend_ema_4h.config import TrendEmaConfig

logger = logging.getLogger(__name__)

_HUNDRED = Decimal("100")


class TrendEmaStrategy:
    """EMA(20)/EMA(50) cross + pullback entry."""

    def __init__(
        self,
        config: TrendEmaConfig,
        risk_engine: RiskEngine,
    ) -> None:
        self._cfg = config
        self._risk = risk_engine
        # P&L tracking.
        self._day_pnl = Decimal("0")
        self._day_trades_count = 0
        self._consecutive_losses = 0
        self._current_day: int | None = None

    def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None:
        candle = ctx.current_candle
        # Сброс счётчиков на смене UTC-дня.
        day = candle.open_time_ms // 86_400_000
        if self._current_day != day:
            self._current_day = day
            self._day_pnl = Decimal("0")
            self._day_trades_count = 0

        if ctx.open_position is not None:
            return None

        history = ctx.history
        min_history = max(self._cfg.ema_slow, self._cfg.atr_window + 1) + 2
        if len(history) < min_history:
            return None

        closes = [c.close for c in history]
        ema_fast = ema(closes, self._cfg.ema_fast)
        ema_slow = ema(closes, self._cfg.ema_slow)
        prev_closes = closes[:-1]
        prev_ema_fast = ema(prev_closes, self._cfg.ema_fast)

        spread_pct = (
            abs(ema_fast - ema_slow) / ema_slow * _HUNDRED if ema_slow > 0 else Decimal("0")
        )
        if spread_pct < Decimal(str(self._cfg.min_ema_spread_pct)):
            return None

        side, signal = self._detect_signal(
            candle=candle,
            history=history,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            prev_ema_fast=prev_ema_fast,
        )
        if signal is None:
            return None

        # ATR-based stop.
        atr_value = atr(list(history[-self._cfg.atr_window - 1 :]), self._cfg.atr_window)
        if atr_value <= 0:
            return None
        sl_distance = atr_value * Decimal(str(self._cfg.sl_atr_multiplier))
        # Минимальная stop_min_pct защита.
        min_sl = candle.close * Decimal(str(self._cfg.stop_min_pct)) / _HUNDRED
        sl_distance = max(sl_distance, min_sl)

        entry = candle.close
        if side == "BUY":
            stop = entry - sl_distance
            tp1 = entry + sl_distance * Decimal(str(self._cfg.tp1_r_multiple))
        else:
            stop = entry + sl_distance
            tp1 = entry - sl_distance * Decimal(str(self._cfg.tp1_r_multiple))

        risk_side = Side.LONG if side == "BUY" else Side.SHORT
        inputs = RiskInputs(
            equity=ctx.equity,
            side=risk_side,
            entry_price=entry,
            stop_price=stop,
            tier=self._cfg.risk_tier,
            day_pnl=self._day_pnl,
            day_trades_count=self._day_trades_count,
            consecutive_losses=self._consecutive_losses,
        )
        decision = self._risk.evaluate(inputs)
        if isinstance(decision, RiskRejection):
            logger.info("trend_ema rejected: %s (%s)", decision.code, decision.reason)
            return None
        assert isinstance(decision, RiskApproval)

        coid = uuid.uuid4().hex[:32]
        return OrderRequest(
            symbol=self._cfg.symbol,
            side=side,
            position_side="LONG" if side == "BUY" else "SHORT",
            order_type="MARKET",
            quantity=decision.quantity,
            attached_stop_loss=stop,
            attached_take_profit=tp1,
            client_order_id=coid,
        )

    def on_fill(self, fill: FillEvent) -> None:
        if fill.reason == "ENTRY":
            return
        self._day_trades_count += 1
        if fill.reason == "STOP_LOSS":
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    # ── Internals ────────────────────────────────────────────────────────

    def _detect_signal(
        self,
        *,
        candle: Kline,
        history: Sequence[Kline],
        ema_fast: Decimal,
        ema_slow: Decimal,
        prev_ema_fast: Decimal,
    ) -> tuple[OrderSide | None, bool | None]:
        """Pullback entry:

        LONG: EMA(20) > EMA(50), предыдущая свеча low ≤ prev_ema_fast
        (touched EMA), текущий close > ema_fast (отскок).

        SHORT: симметрично.

        Возвращает (side, True) если signal, иначе (None, None).
        """
        prev_candle = history[-2]
        if ema_fast > ema_slow:
            touched_below = prev_candle.low <= prev_ema_fast
            current_above = candle.close > ema_fast
            if touched_below and current_above:
                return "BUY", True
        elif ema_fast < ema_slow:
            touched_above = prev_candle.high >= prev_ema_fast
            current_below = candle.close < ema_fast
            if touched_above and current_below:
                return "SELL", True
        return None, None
