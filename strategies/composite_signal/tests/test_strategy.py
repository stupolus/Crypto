"""Unit-тесты CompositeSignalStrategy (план 31).

Проверяем логику композита (2-of-3 консенсус + OI-gate), НЕ edge —
edge на этой стратегии исторически непроверяем (план 31), валидация
forward на демо. Провайдеры — управляемые фейки, без сети.
"""

from __future__ import annotations

from decimal import Decimal

from adapters.bingx.models import Kline
from adapters.bingx.private_models import OrderRequest
from core.backtest import StrategyContext
from core.risk import RiskEngine
from core.signals.liquidation_sweep import LiquidationBucket
from strategies.composite_signal import CompositeSignalStrategy
from strategies.composite_signal.config import CompositeConfig

_STEP = 900_000


def _cfg(**ov: object) -> CompositeConfig:
    base: dict[str, object] = {
        "symbol": "BTC-USDT",
        "timeframe": "15m",
        "funding_min_history": 5,
        "funding_pct_high": 0.8,
        "funding_pct_low": 0.2,
        "liq_spike_min": 3.0,
        "liq_min_baseline_usd": 10.0,
        "liq_baseline_n": 3,
        "oi_lookback": 3,
        "oi_rise_pct": 3.0,
        "oi_fall_pct": 3.0,
        "atr_window": 3,
        "atr_sl_multiplier": 1.5,
        "stop_min_pct": 0.5,
        "tp1_r_multiple": 2.0,
        "risk_tier": "B",
        "direction_bias": "both",
    }
    base.update(ov)
    return CompositeConfig.model_validate(base)


def _k(t: int) -> Kline:
    return Kline.model_validate(
        {"time": t, "open": "100", "high": "101", "low": "99", "close": "100", "volume": "100"}
    )


def _ctx(n: int) -> StrategyContext:
    hist = tuple(_k(i * _STEP) for i in range(n))
    return StrategyContext(
        current_candle=hist[-1], history=hist, equity=Decimal("10000"), open_position=None
    )


class _Funding:
    """Высокий funding в warmup, низкий на свече-триггере (ts >= trig)."""

    def __init__(self, trig_ts: int) -> None:
        self._trig = trig_ts

    def get_funding_rate(self, symbol: str, timestamp_ms: int) -> Decimal | None:
        return Decimal("-0.02") if timestamp_ms >= self._trig else Decimal("0.01")


class _Liq:
    """Sweep с доминированием long-ликвидаций (→ BUY) только на триггере."""

    def __init__(self, trig_ts: int, active: bool = True) -> None:
        self._trig = trig_ts
        self._active = active

    def get_bucket(self, symbol: str, timestamp_ms: int) -> LiquidationBucket | None:
        if not self._active or timestamp_ms < self._trig:
            return None
        return LiquidationBucket(long_volume=Decimal("1000"), short_volume=Decimal("10"))

    def get_baseline(self, symbol: str, timestamp_ms: int, n: int) -> list[LiquidationBucket]:
        return [LiquidationBucket(long_volume=Decimal("20"), short_volume=Decimal("20"))] * n


class _OI:
    def __init__(self, rising: bool) -> None:
        self._rising = rising

    def get_series(self, symbol: str, timestamp_ms: int, n: int) -> list[Decimal]:
        if self._rising:
            return [Decimal(str(1000 + i * 100)) for i in range(12)]
        return [Decimal(str(2000 - i * 100)) for i in range(12)]


def _run(strategy: CompositeSignalStrategy, n_warmup: int, trig_ts: int) -> OrderRequest | None:
    out: OrderRequest | None = None
    for i in range(n_warmup + 1):
        out = strategy.on_candle_close(_ctx(i + 1)) or out
    # последний _ctx(n_warmup+1) — current_candle ts = n_warmup*_STEP.
    return out


def test_warmup_returns_none() -> None:
    s = CompositeSignalStrategy(_cfg(), RiskEngine())
    assert s.on_candle_close(_ctx(3)) is None


def test_no_signals_no_order() -> None:
    """Пустые Static-провайдеры (реальный backtest-случай) → None."""
    s = CompositeSignalStrategy(_cfg(), RiskEngine())
    for i in range(10):
        assert s.on_candle_close(_ctx(i + 1)) is None


def test_single_signal_is_noise() -> None:
    """Только liquidation (funding молчит) → < 2 консенсуса → None."""
    trig = 8 * _STEP
    s = CompositeSignalStrategy(
        _cfg(),
        RiskEngine(),
        funding_provider=None,  # Static → funding всегда None
        liquidation_provider=_Liq(trig),
        oi_provider=_OI(rising=True),
    )
    assert _run(s, 9, trig) is None


def test_consensus_buy_with_oi_gate_emits_order() -> None:
    """funding-low (BUY) + long-liq sweep (BUY) + OI растёт → BUY ордер."""
    trig = 8 * _STEP
    s = CompositeSignalStrategy(
        _cfg(),
        RiskEngine(),
        funding_provider=_Funding(trig),
        liquidation_provider=_Liq(trig),
        oi_provider=_OI(rising=True),
    )
    order = _run(s, 9, trig)
    assert order is not None
    assert order.side == "BUY"
    assert order.attached_take_profit is not None
    assert order.attached_stop_loss is not None
    assert order.attached_take_profit > order.attached_stop_loss


def test_consensus_blocked_by_oi_gate() -> None:
    """Тот же консенсус BUY, но OI падает → gate режет → None."""
    trig = 8 * _STEP
    s = CompositeSignalStrategy(
        _cfg(),
        RiskEngine(),
        funding_provider=_Funding(trig),
        liquidation_provider=_Liq(trig),
        oi_provider=_OI(rising=False),
    )
    assert _run(s, 9, trig) is None


def test_direction_bias_long_only_blocks_short() -> None:
    """funding-high (SELL) + short-liq sweep (SELL), но long_only → None."""
    trig = 8 * _STEP

    class _FundingHigh:
        def get_funding_rate(self, symbol: str, ts: int) -> Decimal | None:
            return Decimal("0.05") if ts >= trig else Decimal("0.001")

    class _LiqShort:
        def get_bucket(self, symbol: str, ts: int) -> LiquidationBucket | None:
            if ts < trig:
                return None
            return LiquidationBucket(long_volume=Decimal("10"), short_volume=Decimal("1000"))

        def get_baseline(self, symbol: str, ts: int, n: int) -> list[LiquidationBucket]:
            return [LiquidationBucket(long_volume=Decimal("20"), short_volume=Decimal("20"))] * n

    s = CompositeSignalStrategy(
        _cfg(direction_bias="long_only"),
        RiskEngine(),
        funding_provider=_FundingHigh(),
        liquidation_provider=_LiqShort(),
        oi_provider=_OI(rising=False),
    )
    assert _run(s, 9, trig) is None
