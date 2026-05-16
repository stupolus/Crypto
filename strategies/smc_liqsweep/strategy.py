"""smc_liqsweep: liquidity-sweep + reclaim reversion (план 32).

Единственный фальсифицируемый элемент SMC: цена прокалывает
swing-экстремум последних `swing_lookback` баров хвостом
≥ `sweep_k_atr`·ATR (сбор ликвидности / стоп-хант), затем
ТЕЛО закрывается ОБРАТНО за уровнем (отказ) → reversion против
свипа. Фильтр: не входить в сильном дневном тренде.

⚠️ CLAUDE.md анти-скальпинг в силе — бэктест-исследование,
НЕ live, НЕ 25x. Скептический априор: SMC в массе — догма;
судим тем же строгим гейтом, что план 31 (см. план 32).
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from adapters.bingx.private_models import OrderRequest
from core.backtest import FillEvent, StrategyContext
from core.risk import RiskApproval, RiskEngine, RiskInputs, RiskRejection, Side
from core.signals import atr, donchian_channel, ema
from strategies.smc_liqsweep.config import SmcLiqsweepConfig

logger = logging.getLogger(__name__)

_HUNDRED = Decimal("100")


class SmcLiqsweepStrategy:
    """Reversion на свипе ликвидности с возвратом за уровень."""

    def __init__(
        self,
        config: SmcLiqsweepConfig,
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
        min_history = (
            max(self._cfg.swing_lookback, self._cfg.ema_slow, self._cfg.atr_window + 1) + 2
        )
        if len(history) < min_history:
            return None

        # Уровень ликвидности — строго из ЗАКРЫТЫХ баров ДО текущего
        # (history[:-1]), иначе look-ahead на собственный бар.
        prior = history[:-1]
        upper, lower = donchian_channel(
            list(prior[-self._cfg.swing_lookback :]), self._cfg.swing_lookback
        )

        # Bounded-window EMA (как scalp_meanrev): без этого O(n²) на 15m.
        calc_n = max(self._cfg.ema_fast, self._cfg.ema_slow) * 6 + 5
        closes = [c.close for c in history[-calc_n:]]
        ema_fast = ema(closes, self._cfg.ema_fast)
        ema_slow = ema(closes, self._cfg.ema_slow)
        if ema_slow <= 0:
            return None

        spread_pct = abs(ema_fast - ema_slow) / ema_slow * _HUNDRED
        if spread_pct > Decimal(str(self._cfg.trend_block_pct)):
            return None

        atr_value = atr(list(history[-self._cfg.atr_window - 1 :]), self._cfg.atr_window)
        if atr_value <= 0:
            return None

        margin = Decimal(str(self._cfg.sweep_k_atr)) * atr_value
        entry = candle.close

        if candle.low < lower - margin and candle.close > lower:
            # Свип лоёв + reclaim → ставка на возврат вверх.
            side, risk_side = "BUY", Side.LONG
            sweep_extreme = candle.low
        elif candle.high > upper + margin and candle.close < upper:
            side, risk_side = "SELL", Side.SHORT
            sweep_extreme = candle.high
        else:
            return None

        buf = Decimal(str(self._cfg.sl_buf_atr)) * atr_value
        min_sl = entry * Decimal(str(self._cfg.stop_min_pct)) / _HUNDRED
        if side == "BUY":
            stop = sweep_extreme - buf
            risk = entry - stop
            if risk < min_sl:
                stop = entry - min_sl
                risk = min_sl
            tp1 = entry + Decimal(str(self._cfg.tp_r)) * risk
        else:
            stop = sweep_extreme + buf
            risk = stop - entry
            if risk < min_sl:
                stop = entry + min_sl
                risk = min_sl
            tp1 = entry - Decimal(str(self._cfg.tp_r)) * risk

        if risk <= 0:
            return None

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
            logger.info("smc_liqsweep rejected: %s (%s)", decision.code, decision.reason)
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
