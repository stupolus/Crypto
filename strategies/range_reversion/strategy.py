"""Range-reversion 4h: торговля в боковике от поддержки к сопротивлению.

Логика (план 25):
- Donchian-канал за channel_n баров: hi/lo/mid.
- Фильтр боковика: |EMA_fast−EMA_slow|/EMA_slow < range_max_spread_pct
  (в тренде range-стратегия сливает на пробое — фильтр обязателен).
- LONG у нижней границы, SHORT у верхней. SL за границей + ATR,
  TP по R-кратности к середине/противоположной стороне.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from adapters.bingx.private_models import OrderRequest
from core.backtest import FillEvent, StrategyContext
from core.risk import RiskApproval, RiskEngine, RiskInputs, RiskRejection, Side
from core.signals import atr, ema
from strategies.range_reversion.config import RangeReversionConfig

logger = logging.getLogger(__name__)

_HUNDRED = Decimal("100")


class RangeReversionStrategy:
    """Mean-reversion в боковике по Donchian-границам."""

    def __init__(
        self,
        config: RangeReversionConfig,
        risk_engine: RiskEngine,
    ) -> None:
        self._cfg = config
        self._risk = risk_engine
        self._day_pnl = Decimal("0")
        self._day_trades_count = 0
        self._consecutive_losses = 0
        self._current_day: int | None = None

    def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None:
        candle = ctx.current_candle
        day = candle.open_time_ms // 86_400_000
        if self._current_day != day:
            self._current_day = day
            self._day_pnl = Decimal("0")
            self._day_trades_count = 0

        if ctx.open_position is not None:
            return None

        history = ctx.history
        min_history = max(self._cfg.channel_n, self._cfg.ema_slow, self._cfg.atr_window + 1) + 2
        if len(history) < min_history:
            return None

        window = history[-self._cfg.channel_n - 1 : -1]  # без текущей свечи
        hi = max(c.high for c in window)
        lo = min(c.low for c in window)
        if hi <= lo:
            return None

        closes = [c.close for c in history]
        ema_fast = ema(closes, self._cfg.ema_fast)
        ema_slow = ema(closes, self._cfg.ema_slow)
        spread_pct = abs(ema_fast - ema_slow) / ema_slow * _HUNDRED if ema_slow > 0 else _HUNDRED
        # Фильтр режима: торгуем только в боковике.
        if spread_pct >= Decimal(str(self._cfg.range_max_spread_pct)):
            return None

        buf = Decimal(str(self._cfg.band_buffer_pct)) / _HUNDRED
        entry = candle.close
        side: str | None = None
        if entry <= lo * (1 + buf):
            side = "BUY"
        elif entry >= hi * (1 - buf):
            side = "SELL"
        if side is None:
            return None

        atr_value = atr(list(history[-self._cfg.atr_window - 1 :]), self._cfg.atr_window)
        if atr_value <= 0:
            return None
        sl_pad = atr_value * Decimal(str(self._cfg.sl_atr_multiplier))
        min_sl = entry * Decimal(str(self._cfg.stop_min_pct)) / _HUNDRED

        if side == "BUY":
            stop = lo - sl_pad
            sl_dist = max(entry - stop, min_sl)
            stop = entry - sl_dist
            tp1 = entry + sl_dist * Decimal(str(self._cfg.tp1_r_multiple))
            risk_side = Side.LONG
        else:
            stop = hi + sl_pad
            sl_dist = max(stop - entry, min_sl)
            stop = entry + sl_dist
            tp1 = entry - sl_dist * Decimal(str(self._cfg.tp1_r_multiple))
            risk_side = Side.SHORT

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
            logger.info("range_reversion rejected: %s (%s)", decision.code, decision.reason)
            return None
        assert isinstance(decision, RiskApproval)

        return OrderRequest(
            symbol=self._cfg.symbol,
            side=side,
            order_type="MARKET",
            quantity=decision.quantity,
            attached_stop_loss=stop,
            attached_take_profit=tp1,
            client_order_id=uuid.uuid4().hex[:32],
        )

    def on_fill(self, fill: FillEvent) -> None:
        if fill.reason == "ENTRY":
            return
        self._day_trades_count += 1
        if fill.reason == "STOP_LOSS":
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
