"""composite_signal — стратегия принципа 3 (план 31).

Один скринер = шум; ≥2 ортогональных сигнала = сигнал. Использует
ТОЛЬКО готовые протестированные примитивы core/signals:

- ``detect_funding_extreme`` — contrarian по funding percentile.
- ``detect_liquidation_sweep`` — каскад ликвидаций.
- ``aggregate_extended_signals`` — 2-of-3 консенсус (order_flow не
  подаём: нет провайдера bid/ask — консенсус из funding+liquidation).
- ``detect_oi_trend`` — gate направления (не голос).

⚠️ Историческая валидация невозможна (нет рядов OI/liq/CVD —
план 31). Реализует ``Strategy`` protocol: один и тот же код в
unit-тестах (Static-провайдеры) и в live/демо forward-тесте.
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum

from adapters.bingx.models import Kline
from adapters.bingx.private_models import OrderRequest, OrderSide
from core.backtest import FillEvent, StrategyContext
from core.risk import RiskApproval, RiskEngine, RiskInputs, RiskRejection, Side
from core.signals import (
    DeltaProvider,
    FundingExtremeConfig,
    FundingExtremeSignal,
    FundingProvider,
    LiquidationProvider,
    LiquidationSweepConfig,
    LiquidationSweepSignal,
    OIState,
    OpenInterestConfig,
    OpenInterestProvider,
    OrderFlowConfig,
    OrderFlowSignal,
    StaticDeltaProvider,
    StaticFundingProvider,
    StaticLiquidationProvider,
    StaticOpenInterestProvider,
    aggregate_extended_signals,
    atr,
    detect_funding_extreme,
    detect_liquidation_sweep,
    detect_oi_trend,
    detect_order_flow,
    percentile_rank,
)
from strategies.composite_signal.config import CompositeConfig

logger = logging.getLogger(__name__)

_HUNDRED = Decimal("100")
_DAY_MS = 86_400_000


class _State(StrEnum):
    FLAT = "FLAT"
    PENDING = "PENDING"
    OPEN = "OPEN"


class CompositeSignalStrategy:
    """Composite 2-of-3 (funding + liquidation) + OI-gate (план 31)."""

    def __init__(
        self,
        config: CompositeConfig,
        risk_engine: RiskEngine,
        *,
        funding_provider: FundingProvider | None = None,
        liquidation_provider: LiquidationProvider | None = None,
        oi_provider: OpenInterestProvider | None = None,
        delta_provider: DeltaProvider | None = None,
    ) -> None:
        self._cfg = config
        self._risk = risk_engine
        self._funding = funding_provider or StaticFundingProvider()
        self._liq = liquidation_provider or StaticLiquidationProvider()
        self._oi = oi_provider or StaticOpenInterestProvider()
        self._delta = delta_provider or StaticDeltaProvider()

        self._state = _State.FLAT
        self._pending_coid: str | None = None
        # Стратегия копит funding-историю из провайдера (работает и в
        # live/forward, и в тесте — без отдельного History-протокола).
        self._funding_hist: deque[Decimal] = deque(maxlen=config.funding_min_history * 3)

        self._day_pnl = Decimal("0")
        self._day_trades_count = 0
        self._consecutive_losses = 0
        self._current_utc_day: int | None = None

    # ── Strategy protocol ─────────────────────────────────────────────────

    def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None:
        candle = ctx.current_candle
        ts = candle.open_time_ms
        self._roll_day_if_needed(ts)

        # Копим funding-историю всегда (даже в позиции).
        cur_funding = self._funding.get_funding_rate(self._cfg.symbol, ts)
        if cur_funding is not None:
            self._funding_hist.append(cur_funding)

        if ctx.open_position is not None:
            self._state = _State.OPEN
            return None
        if self._state == _State.PENDING:
            return None
        self._state = _State.FLAT

        min_history = max(self._cfg.atr_window + 1, self._cfg.liq_baseline_n) + 1
        if len(ctx.history) < min_history:
            return None

        funding_sig = self._funding_signal(cur_funding)
        liq_sig = self._liquidation_signal(ts)
        of_sig = self._order_flow_signal(ts)

        result = aggregate_extended_signals(
            symbol=self._cfg.symbol,
            timestamp_ms=ts,
            funding_signal=funding_sig,
            order_flow_signal=of_sig,
            liquidation_signal=liq_sig,
        )
        if result.candidate is None:
            return None

        # 43.1 Confidence-gate (v2; default min_confidence=0 → no-op).
        confidence = result.candidate.confidence_raw
        if not self._confidence_ok(confidence):
            return None

        side: OrderSide = "BUY" if result.candidate.action == "BUY" else "SELL"
        if self._cfg.direction_bias == "long_only" and side == "SELL":
            return None
        if self._cfg.direction_bias == "short_only" and side == "BUY":
            return None
        if not self._oi_gate_passes(side, ts):
            return None
        # 43.3 ATR-percentile режим-фильтр (v2; default [0,1] → no-op).
        if not self._atr_regime_ok(ctx.history[:-1]):
            return None

        entry = candle.close
        stop = self._compute_stop(entry, side, ctx.history[:-1])
        tp1 = self._compute_tp1(entry, stop, side, confidence)
        risk_side = Side.LONG if side == "BUY" else Side.SHORT

        decision = self._risk.evaluate(
            RiskInputs(
                equity=ctx.equity,
                side=risk_side,
                entry_price=entry,
                stop_price=stop,
                take_profit_price=tp1,
                tier=self._cfg.risk_tier,
                day_pnl=self._day_pnl,
                day_trades_count=self._day_trades_count,
                consecutive_losses=self._consecutive_losses,
            )
        )
        if isinstance(decision, RiskRejection):
            logger.info("composite_signal rejected by RiskEngine: %s", decision.code)
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
            attached_take_profit=tp1,
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

    # ── Helpers ──────────────────────────────────────────────────────────

    def _funding_signal(self, cur_funding: Decimal | None) -> FundingExtremeSignal | None:
        if cur_funding is None or len(self._funding_hist) < self._cfg.funding_min_history:
            return None
        hist = list(self._funding_hist)[:-1]  # без текущего
        if len(hist) < self._cfg.funding_min_history:
            return None
        return detect_funding_extreme(
            cur_funding,
            hist,
            FundingExtremeConfig(
                percentile_high=Decimal(str(self._cfg.funding_pct_high)),
                percentile_low=Decimal(str(self._cfg.funding_pct_low)),
                min_history=self._cfg.funding_min_history,
            ),
        )

    def _liquidation_signal(self, ts: int) -> LiquidationSweepSignal | None:
        bucket = self._liq.get_bucket(self._cfg.symbol, ts)
        if bucket is None:
            return None
        baseline = self._liq.get_baseline(self._cfg.symbol, ts, self._cfg.liq_baseline_n)
        if not baseline:
            return None
        return detect_liquidation_sweep(
            bucket,
            baseline,
            LiquidationSweepConfig(
                spike_threshold=Decimal(str(self._cfg.liq_spike_min)),
                min_baseline=Decimal(str(self._cfg.liq_min_baseline_usd)),
                min_history=self._cfg.liq_baseline_n,
            ),
        )

    def _order_flow_signal(self, ts: int) -> OrderFlowSignal | None:
        cvd = self._delta.get_cvd_series(self._cfg.symbol, ts, self._cfg.cvd_lookback)
        if len(cvd) < 2:
            return None
        # CVD кумулятивен: per-bar приращения → buy/sell давление.
        buy = Decimal("0")
        sell = Decimal("0")
        for i in range(1, len(cvd)):
            d = cvd[i] - cvd[i - 1]
            if d > 0:
                buy += d
            else:
                sell += -d
        return detect_order_flow(
            buy, sell, OrderFlowConfig(threshold=Decimal(str(self._cfg.order_flow_threshold)))
        )

    def _oi_gate_passes(self, side: OrderSide, ts: int) -> bool:
        series = self._oi.get_series(self._cfg.symbol, ts, self._cfg.oi_lookback * 4)
        sig = detect_oi_trend(
            series,
            OpenInterestConfig(
                rise_pct=Decimal(str(self._cfg.oi_rise_pct)),
                fall_pct=Decimal(str(self._cfg.oi_fall_pct)),
                lookback=self._cfg.oi_lookback,
            ),
        )
        if sig is None:
            return False
        if side == "SELL":
            return sig.state == OIState.FALLING
        return sig.state != OIState.FALLING

    def _compute_stop(self, entry: Decimal, side: OrderSide, closed: Sequence[Kline]) -> Decimal:
        a = atr(closed, self._cfg.atr_window)
        sl_dist = a * Decimal(str(self._cfg.atr_sl_multiplier))
        min_dist = entry * Decimal(str(self._cfg.stop_min_pct)) / _HUNDRED
        dist = max(sl_dist, min_dist)
        return entry - dist if side == "BUY" else entry + dist

    def _compute_tp1(
        self, entry: Decimal, stop: Decimal, side: OrderSide, confidence: float
    ) -> Decimal:
        dist = abs(entry - stop)
        if self._cfg.tp1_r_adaptive:
            # 43.2 R линейно от силы сигнала: r_min..r_max по confidence.
            r_min = self._cfg.tp1_r_min or self._cfg.tp1_r_multiple
            r_max = self._cfg.tp1_r_max or self._cfg.tp1_r_multiple
            c = min(max(confidence, 0.0), 1.0)
            r = Decimal(str(r_min + (r_max - r_min) * c))
        else:
            r = Decimal(str(self._cfg.tp1_r_multiple))
        return entry + r * dist if side == "BUY" else entry - r * dist

    def _confidence_ok(self, confidence: float) -> bool:
        """43.1 v2 confidence-gate. Default min_confidence=0 → всегда True."""
        return confidence >= self._cfg.min_confidence

    def _atr_regime_ok(self, closed: Sequence[Kline]) -> bool:
        """43.3 ATR-percentile фильтр режима. Default [0,1] → True (выкл)."""
        lo = self._cfg.atr_pct_min
        hi = self._cfg.atr_pct_max
        if lo <= 0.0 and hi >= 1.0:
            return True
        w = self._cfg.atr_window
        lookback = self._cfg.atr_pct_lookback
        if len(closed) < w + 2:
            return False
        atr_now = atr(closed, w)
        atrs: list[Decimal] = []
        for end in range(w + 1, len(closed) + 1):
            window = closed[max(0, end - (w + 1)) : end]
            if len(window) < w + 1:
                continue
            atrs.append(atr(window, w))
            if len(atrs) >= lookback:
                break
        if not atrs:
            return False
        rank = percentile_rank(atrs, atr_now)
        return Decimal(str(lo)) <= rank <= Decimal(str(hi))

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
