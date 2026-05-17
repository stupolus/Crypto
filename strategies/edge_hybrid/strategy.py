"""edge_hybrid: объединение scalp (A) ∨ liquidity-sweep (B), план 33.

Ветка B (свип ликвидности + reclaim) имеет приоритет над A
(mean-reversion к EMA-якорю) при конфликте в одном баре — свип
структурно сильнее. Общий фильтр тренда, общий риск/выход.
DOLF-фильтр — фаза 33.2 (здесь ещё нет).

⚠️ CLAUDE.md анти-скальпинг в силе — бэктест/demo-исследование,
НЕ live, НЕ 25x. Промежуточный гейт ≥60 — веха, не edge (план 33).
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from adapters.bingx.private_models import OrderRequest
from core.backtest import FillEvent, StrategyContext
from core.risk import RiskApproval, RiskEngine, RiskInputs, RiskRejection, Side
from core.signals import atr, donchian_channel, ema
from strategies.edge_hybrid.config import EdgeHybridConfig

logger = logging.getLogger(__name__)

_HUNDRED = Decimal("100")


class EdgeHybridStrategy:
    """scalp mean-reversion ∨ liquidity-sweep reclaim, общий риск."""

    def __init__(
        self,
        config: EdgeHybridConfig,
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
            # «3 убытка подряд = стоп ДО ЗАВТРА» (риск-профиль.md):
            # на новом дне счётчик обязан обнуляться. Без этого
            # circuit breaker был ВЕЧНЫМ → стратегия умирала после
            # 3 лоссов на весь бэктест (корень «нет статбазы» 31–33).
            self._consecutive_losses = 0

        if ctx.open_position is not None:
            return None

        cfg = self._cfg
        history = ctx.history
        min_history = (
            max(
                cfg.anchor_ema,
                cfg.ema_slow,
                cfg.swing_lookback,
                cfg.box_window,
                cfg.atr_window + 1,
            )
            + 2
        )
        if len(history) < min_history:
            return None

        # Bounded-window EMA: без этого бэктест O(n²) на 15m.
        calc_n = max(cfg.anchor_ema, cfg.ema_slow) * 6 + 5
        closes = [c.close for c in history[-calc_n:]]
        anchor = ema(closes, cfg.anchor_ema)
        ema_fast = ema(closes, cfg.ema_fast)
        ema_slow = ema(closes, cfg.ema_slow)
        if anchor <= 0 or ema_slow <= 0:
            return None

        # Reversion-ветки (A,B) требуют спокойного режима; пробойная
        # ветка C — НЕТ (иначе все сделки кучкуются в те же недели,
        # диагноз 33.1). Поэтому не ранний return, а флаг.
        spread_pct = abs(ema_fast - ema_slow) / ema_slow * _HUNDRED
        trend_ok = spread_pct <= Decimal(str(cfg.trend_block_pct))

        atr_value = atr(list(history[-cfg.atr_window - 1 :]), cfg.atr_window)
        if atr_value <= 0:
            return None

        entry = candle.close

        # --- Ветка B (приоритет): свип ликвидности + reclaim ---
        prior = history[:-1]
        upper, lower = donchian_channel(list(prior[-cfg.swing_lookback :]), cfg.swing_lookback)
        margin = Decimal(str(cfg.sweep_k_atr)) * atr_value
        side: str | None = None
        risk_side: Side | None = None
        stop: Decimal = Decimal("0")
        tp1: Decimal = Decimal("0")

        if cfg.enable_b and trend_ok and candle.low < lower - margin and candle.close > lower:
            side, risk_side = "BUY", Side.LONG
            buf = Decimal(str(cfg.sl_buf_atr)) * atr_value
            min_sl = entry * Decimal(str(cfg.stop_min_pct)) / _HUNDRED
            stop = candle.low - buf
            risk = entry - stop
            if risk < min_sl:
                stop = entry - min_sl
                risk = min_sl
            tp1 = entry + Decimal(str(cfg.tp_r)) * risk
        elif cfg.enable_b and trend_ok and candle.high > upper + margin and candle.close < upper:
            side, risk_side = "SELL", Side.SHORT
            buf = Decimal(str(cfg.sl_buf_atr)) * atr_value
            min_sl = entry * Decimal(str(cfg.stop_min_pct)) / _HUNDRED
            stop = candle.high + buf
            risk = stop - entry
            if risk < min_sl:
                stop = entry + min_sl
                risk = min_sl
            tp1 = entry - Decimal(str(cfg.tp_r)) * risk

        # --- Ветка C: пробой бокса консолидации + volume-bias ---
        # (PR #152 #008). Независима от trend_ok — структурно иной
        # триггер, размазывает сделки по другим неделям (диагноз 33.1).
        if side is None and cfg.enable_c:
            box_bars = prior[-cfg.box_window :]
            box_high = max(c.high for c in box_bars)
            box_low = min(c.low for c in box_bars)
            box_h = box_high - box_low
            up_vol = sum((c.volume for c in box_bars if c.close > c.open), Decimal("0"))
            dn_vol = sum((c.volume for c in box_bars if c.close < c.open), Decimal("0"))
            c_range = candle.high - candle.low
            body = abs(candle.close - candle.open)
            tight = Decimal("0") < box_h <= Decimal(str(cfg.box_max_atr)) * atr_value
            strong = c_range > 0 and body / c_range >= Decimal(str(cfg.strong_body_frac))
            min_sl = entry * Decimal(str(cfg.stop_min_pct)) / _HUNDRED
            if tight and strong and candle.close > box_high and up_vol > dn_vol:
                side, risk_side = "BUY", Side.LONG
                stop = box_low
                risk = entry - stop
                if risk < min_sl:
                    stop = entry - min_sl
                    risk = min_sl
                tp1 = entry + Decimal(str(cfg.box_tp_r)) * risk
            elif tight and strong and candle.close < box_low and dn_vol > up_vol:
                side, risk_side = "SELL", Side.SHORT
                stop = box_high
                risk = stop - entry
                if risk < min_sl:
                    stop = entry + min_sl
                    risk = min_sl
                tp1 = entry - Decimal(str(cfg.box_tp_r)) * risk

        # --- Ветка A: mean-reversion к якорю (если B/C не сработали) ---
        if side is None and cfg.enable_a and trend_ok:
            dev = entry - anchor
            thr = Decimal(str(cfg.entry_k_atr)) * atr_value
            sl_dist = Decimal(str(cfg.sl_k_atr)) * atr_value
            min_sl = entry * Decimal(str(cfg.stop_min_pct)) / _HUNDRED
            sl_dist = max(sl_dist, min_sl)
            if dev <= -thr:
                side, risk_side = "BUY", Side.LONG
                stop = entry - sl_dist
                tp1 = anchor
            elif dev >= thr:
                side, risk_side = "SELL", Side.SHORT
                stop = entry + sl_dist
                tp1 = anchor

        if side is None or risk_side is None:
            return None
        if stop <= 0 or (side == "BUY" and stop >= entry) or (side == "SELL" and stop <= entry):
            return None

        inputs = RiskInputs(
            equity=ctx.equity,
            side=risk_side,
            entry_price=entry,
            stop_price=stop,
            tier=cfg.risk_tier,
            day_pnl=self._day_pnl,
            day_trades_count=self._day_trades_count,
            consecutive_losses=self._consecutive_losses,
        )
        decision = self._risk.evaluate(inputs)
        if isinstance(decision, RiskRejection):
            logger.info("edge_hybrid rejected: %s (%s)", decision.code, decision.reason)
            return None
        assert isinstance(decision, RiskApproval)

        if cfg.entry_order_type == "LIMIT":
            return OrderRequest(
                symbol=cfg.symbol,
                side=side,
                order_type="LIMIT",
                quantity=decision.quantity,
                price=entry,  # maker: своя цена = close сигнал-бара
                attached_stop_loss=stop,
                attached_take_profit=tp1,
                client_order_id=uuid.uuid4().hex[:32],
            )
        return OrderRequest(
            symbol=cfg.symbol,
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
