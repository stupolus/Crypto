"""liquidation_reversal — методология Щукина (план 21).

Composite ТОЛЬКО из готовых примитивов:
- ``detect_liquidation_sweep`` — триггер (крупная свеча ликвидаций)
- ``donchian_channel`` — «значимый экстремум» (хай/лой за level_n)
- ``detect_oi_trend`` — gate направления
- CVD (DeltaProvider) — подтверждение
- funding (FundingProvider) — фильтр шортов

Сетапы:
- A1 LONG: close ≤ donchian_low, long-ликвидации sweep, цикл завершён,
  OI не падает, CVD вверх.
- A2 SHORT: close ≥ donchian_high, short-ликвидации sweep, цикл
  завершён, OI ПАДАЕТ (жёсткий gate), CVD вниз, funding не глубоко
  отрицательный.

Данные — через DI-провайдеры (план 21 фаза 21.1), привязка по
``candle.open_time_ms``. Анти-look-ahead: providers отдают только
данные ≤ ts (тесты в test_liq_reversal_providers).

Реализует ``Strategy`` protocol — backtest и live без изменений.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from adapters.bingx.private_models import OrderRequest, OrderSide
from core.backtest import FillEvent, StrategyContext
from core.risk import (
    RiskApproval,
    RiskEngine,
    RiskInputs,
    RiskRejection,
    Side,
)
from core.signals import (
    DeltaProvider,
    FundingProvider,
    LiquidationProvider,
    LiquidationSweepConfig,
    LiquidationSweepSignal,
    OIState,
    OpenInterestConfig,
    OpenInterestProvider,
    StaticDeltaProvider,
    StaticFundingProvider,
    StaticLiquidationProvider,
    StaticOpenInterestProvider,
    detect_liquidation_sweep,
    detect_oi_trend,
    donchian_channel,
)
from strategies.liquidation_reversal.config import LiqReversalConfig

logger = logging.getLogger(__name__)

_HUNDRED = Decimal("100")
_DAY_MS = 86_400_000


class _State(StrEnum):
    FLAT = "FLAT"
    PENDING = "PENDING"
    OPEN = "OPEN"


@dataclass
class _PendingSetup:
    """Зафиксированный sweep, ждём завершения цикла + подтверждения."""

    side: OrderSide
    level_price: Decimal  # donchian ref для structural SL
    bars_since: int


class LiquidationReversalStrategy:
    """Разворот от каскада ликвидаций на экстремуме (план 21 A1/A2)."""

    def __init__(
        self,
        config: LiqReversalConfig,
        risk_engine: RiskEngine,
        *,
        liquidation_provider: LiquidationProvider | None = None,
        oi_provider: OpenInterestProvider | None = None,
        delta_provider: DeltaProvider | None = None,
        funding_provider: FundingProvider | None = None,
    ) -> None:
        self._cfg = config
        self._risk = risk_engine
        self._liq = liquidation_provider or StaticLiquidationProvider()
        self._oi = oi_provider or StaticOpenInterestProvider()
        self._delta = delta_provider or StaticDeltaProvider()
        self._funding = funding_provider or StaticFundingProvider()

        self._state = _State.FLAT
        self._pending_coid: str | None = None
        self._setup: _PendingSetup | None = None

        self._day_pnl = Decimal("0")
        self._day_trades_count = 0
        self._consecutive_losses = 0
        self._current_utc_day: int | None = None

    # ── Strategy protocol ─────────────────────────────────────────────────

    def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None:
        candle = ctx.current_candle
        self._roll_day_if_needed(candle.open_time_ms)

        if ctx.open_position is not None:
            self._state = _State.OPEN
            self._setup = None
            return None
        if self._state == _State.PENDING:
            return None
        self._state = _State.FLAT

        min_history = self._cfg.level_n + 2
        if len(ctx.history) < min_history:
            return None

        ts = candle.open_time_ms
        closed = ctx.history[:-1]
        upper, lower = donchian_channel(closed, self._cfg.level_n)

        # Если есть pending setup — продвигаем цикл и проверяем подтверждение.
        if self._setup is not None:
            self._setup.bars_since += 1
            if self._setup.bars_since < self._cfg.cycle_wait_bars:
                return None
            # Цикл завершён — проверяем подтверждение, иначе сбрасываем.
            order = self._try_confirm_and_enter(ctx, ts)
            # timeout: не подтвердилось за 2×cycle_wait — дроп setup
            if (
                order is None
                and self._setup is not None
                and self._setup.bars_since > self._cfg.cycle_wait_bars * 2
            ):
                self._setup = None
            return order

        # Нет setup — ищем триггер (sweep на экстремуме).
        sweep = self._detect_sweep(ts)
        if sweep is None:
            return None

        long_trigger = sweep.action == "BUY" and candle.close <= lower
        short_trigger = sweep.action == "SELL" and candle.close >= upper
        if self._cfg.direction_bias == "long_only":
            short_trigger = False
        elif self._cfg.direction_bias == "short_only":
            long_trigger = False
        if not (long_trigger or short_trigger):
            return None

        side: OrderSide = "BUY" if long_trigger else "SELL"
        self._setup = _PendingSetup(
            side=side,
            level_price=lower if long_trigger else upper,
            bars_since=0,
        )
        # Не входим в свечу sweep — ждём цикл (cycle_wait_bars).
        return None

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
        self._setup = None

    # ── Helpers ──────────────────────────────────────────────────────────

    def _detect_sweep(self, ts: int) -> LiquidationSweepSignal | None:
        bucket = self._liq.get_bucket(self._cfg.symbol, ts)
        if bucket is None:
            return None
        baseline = self._liq.get_baseline(self._cfg.symbol, ts, self._cfg.liq_baseline_n)
        if not baseline:
            return None
        cfg = LiquidationSweepConfig(
            spike_threshold=Decimal(str(self._cfg.liq_spike_min)),
            min_baseline=Decimal(str(self._cfg.liq_min_baseline_usd)),
            min_history=self._cfg.liq_baseline_n,
        )
        return detect_liquidation_sweep(bucket, baseline, cfg)

    def _try_confirm_and_enter(self, ctx: StrategyContext, ts: int) -> OrderRequest | None:
        assert self._setup is not None
        setup = self._setup
        candle = ctx.current_candle

        if not self._oi_gate_passes(setup.side, ts):
            return None
        if not self._cvd_confirms(setup.side, ts):
            return None
        if setup.side == "SELL" and not self._funding_allows_short(ts):
            return None

        entry = candle.close
        risk_side = Side.LONG if setup.side == "BUY" else Side.SHORT
        stop = self._compute_stop(entry, setup.side, setup.level_price)
        tp1 = self._compute_tp1(entry, stop, setup.side)

        decision = self._risk.evaluate(
            RiskInputs(
                equity=ctx.equity,
                side=risk_side,
                entry_price=entry,
                stop_price=stop,
                tier=self._cfg.risk_tier,
                day_pnl=self._day_pnl,
                day_trades_count=self._day_trades_count,
                consecutive_losses=self._consecutive_losses,
            )
        )
        if isinstance(decision, RiskRejection):
            logger.info("liq_reversal rejected by RiskEngine: %s", decision.code)
            self._setup = None
            return None
        assert isinstance(decision, RiskApproval)

        coid = uuid.uuid4().hex[:32]
        self._pending_coid = coid
        self._state = _State.PENDING
        self._setup = None
        return OrderRequest(
            symbol=self._cfg.symbol,
            side=setup.side,
            order_type="MARKET",
            quantity=decision.quantity,
            attached_stop_loss=stop,
            attached_take_profit=tp1,
            client_order_id=coid,
        )

    def _oi_gate_passes(self, side: OrderSide, ts: int) -> bool:
        if not self._cfg.oi_gate_enabled:
            return True
        series = self._oi.get_series(self._cfg.symbol, ts, self._cfg.oi_lookback * 4)
        oi_cfg = OpenInterestConfig(
            rise_pct=Decimal(str(self._cfg.oi_rise_pct)),
            fall_pct=Decimal(str(self._cfg.oi_fall_pct)),
            lookback=self._cfg.oi_lookback,
        )
        sig = detect_oi_trend(series, oi_cfg)
        if sig is None:
            return False
        if side == "SELL":
            # Жёсткий gate: шорт только на падающем OI.
            return sig.state == OIState.FALLING
        # LONG: OI не должен падать (перестал падать / растёт).
        return sig.state != OIState.FALLING

    def _cvd_confirms(self, side: OrderSide, ts: int) -> bool:
        cvd = self._delta.get_cvd_series(self._cfg.symbol, ts, self._cfg.cvd_lookback)
        if len(cvd) < 2:
            return False
        change = cvd[-1] - cvd[0]
        # LONG: покупатель появился (CVD вверх). SHORT: продавец (вниз).
        return change > 0 if side == "BUY" else change < 0

    def _funding_allows_short(self, ts: int) -> bool:
        funding = self._funding.get_funding_rate(self._cfg.symbol, ts)
        if funding is None:
            return True
        # Не шортить в глубоко негативный funding («фаза дойки»).
        return funding > Decimal(str(self._cfg.funding_short_block))

    def _compute_stop(self, entry: Decimal, side: OrderSide, level_price: Decimal) -> Decimal:
        """Structural SL — за экстремум (level) ИЛИ min %, что дальше."""
        min_dist = entry * Decimal(str(self._cfg.stop_min_pct)) / _HUNDRED
        if side == "BUY":
            return min(level_price, entry - min_dist)
        return max(level_price, entry + min_dist)

    def _compute_tp1(self, entry: Decimal, stop: Decimal, side: OrderSide) -> Decimal:
        dist = abs(entry - stop)
        r = Decimal(str(self._cfg.tp1_r_multiple))
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
