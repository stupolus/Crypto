"""scalp_meanrev: 15m mean-reversion к EMA-якорю (план 31).

Вход: |close − EMA(anchor)| ≥ entry_k·ATR → ставка на возврат
(ниже якоря → BUY, выше → SELL). Обязательный фильтр: НЕ
скальпить в сильном тренде дня (|EMAf−EMAs|/EMAs > trend_block).
Выход: TP = якорь (возврат), SL = entry ± sl_k·ATR.

⚠️ CLAUDE.md анти-скальпинг в силе — это бэктест-исследование,
НЕ live, НЕ 25x. Валидация — строгий гейт + cost-sweep (план 31).
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from adapters.bingx.private_models import OrderRequest
from core.backtest import FillEvent, StrategyContext
from core.risk import RiskApproval, RiskEngine, RiskInputs, RiskRejection, Side
from core.signals import atr, ema
from strategies.scalp_meanrev.config import ScalpMeanrevConfig

logger = logging.getLogger(__name__)

_HUNDRED = Decimal("100")


class ScalpMeanrevStrategy:
    """Высокочастотная mean-reversion к EMA-якорю на мелком ТФ."""

    def __init__(
        self,
        config: ScalpMeanrevConfig,
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
        min_history = max(self._cfg.anchor_ema, self._cfg.ema_slow, self._cfg.atr_window + 1) + 2
        if len(history) < min_history:
            return None

        # Окно расчёта: windowed-EMA сходится экспоненциально, хвоста
        # ~6·period достаточно для машинной точности. Без этого
        # бэктест O(n²) по растущей истории (нежизнеспособно на 15m).
        calc_n = max(self._cfg.anchor_ema, self._cfg.ema_slow) * 6 + 5
        closes = [c.close for c in history[-calc_n:]]
        anchor = ema(closes, self._cfg.anchor_ema)
        ema_fast = ema(closes, self._cfg.ema_fast)
        ema_slow = ema(closes, self._cfg.ema_slow)
        if anchor <= 0 or ema_slow <= 0:
            return None

        # Фильтр режима: в сильном тренде дня mean-reversion сливает.
        spread_pct = abs(ema_fast - ema_slow) / ema_slow * _HUNDRED
        if spread_pct > Decimal(str(self._cfg.trend_block_pct)):
            return None

        atr_value = atr(list(history[-self._cfg.atr_window - 1 :]), self._cfg.atr_window)
        if atr_value <= 0:
            return None

        entry = candle.close
        dev = entry - anchor
        thr = Decimal(str(self._cfg.entry_k_atr)) * atr_value
        if dev <= -thr:
            side, risk_side = "BUY", Side.LONG
        elif dev >= thr:
            side, risk_side = "SELL", Side.SHORT
        else:
            return None

        sl_dist = Decimal(str(self._cfg.sl_k_atr)) * atr_value
        min_sl = entry * Decimal(str(self._cfg.stop_min_pct)) / _HUNDRED
        sl_dist = max(sl_dist, min_sl)

        if side == "BUY":
            stop = entry - sl_dist
            tp1 = anchor  # цель — возврат к якорю
        else:
            stop = entry + sl_dist
            tp1 = anchor

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
            logger.info("scalp_meanrev rejected: %s (%s)", decision.code, decision.reason)
            return None
        assert isinstance(decision, RiskApproval)

        return OrderRequest(
            symbol=self._cfg.symbol,
            side=side,
            position_side="LONG" if side == "BUY" else "SHORT",
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
