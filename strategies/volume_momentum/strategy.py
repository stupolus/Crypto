"""volume_momentum 4h: всплеск объёма + направленная свеча → импульс.

Бэктестируемая суть дискреционного сетапа пользователя («объём
есть → движение продолжается»), очищенная от невалидируемого
(стакан) и запрещённого (скальпинг +0.1% на 5m, анти-скальпинг.md).

Вход: объём бара > vol_mult × средний объём за vol_n И свеча
направленная (close>open → LONG; close<open → SHORT).
Выход: SL=ATR×k, TP=R×SL.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from adapters.bingx.private_models import OrderRequest
from core.backtest import FillEvent, StrategyContext
from core.risk import RiskApproval, RiskEngine, RiskInputs, RiskRejection, Side
from core.signals import atr
from strategies.volume_momentum.config import VolumeMomentumConfig

logger = logging.getLogger(__name__)

_HUNDRED = Decimal("100")


class VolumeMomentumStrategy:
    """Объём-подтверждённый импульс."""

    def __init__(
        self,
        config: VolumeMomentumConfig,
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
        min_history = max(self._cfg.vol_n, self._cfg.atr_window + 1) + 2
        if len(history) < min_history:
            return None

        prior = history[-self._cfg.vol_n - 1 : -1]  # без текущей свечи
        # Объём — не деньги/цена: float достаточно (без Decimal-смешения).
        avg_vol = sum(float(c.volume) for c in prior) / len(prior)
        if avg_vol <= 0:
            return None
        spike = float(candle.volume) > avg_vol * self._cfg.vol_mult
        if not spike:
            return None

        if candle.close > candle.open:
            side = "BUY"
        elif candle.close < candle.open:
            side = "SELL"
        else:
            return None

        atr_value = atr(list(history[-self._cfg.atr_window - 1 :]), self._cfg.atr_window)
        if atr_value <= 0:
            return None
        sl_dist = atr_value * Decimal(str(self._cfg.sl_atr_multiplier))
        min_sl = candle.close * Decimal(str(self._cfg.stop_min_pct)) / _HUNDRED
        sl_dist = max(sl_dist, min_sl)

        entry = candle.close
        if side == "BUY":
            stop = entry - sl_dist
            tp1 = entry + sl_dist * Decimal(str(self._cfg.tp1_r_multiple))
            risk_side = Side.LONG
        else:
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
            logger.info("volume_momentum rejected: %s (%s)", decision.code, decision.reason)
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
