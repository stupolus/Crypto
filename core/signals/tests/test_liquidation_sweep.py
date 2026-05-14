"""Unit-тесты ``detect_liquidation_sweep``."""

from __future__ import annotations

from decimal import Decimal

from core.signals.liquidation_sweep import (
    LiquidationBucket,
    LiquidationSweepConfig,
    detect_liquidation_sweep,
)


def _baseline(n: int = 12, long_v: str = "500", short_v: str = "500") -> list[LiquidationBucket]:
    return [
        LiquidationBucket(long_volume=Decimal(long_v), short_volume=Decimal(short_v))
        for _ in range(n)
    ]


def test_long_cascade_returns_buy() -> None:
    """5x baseline и long-side dominates → BUY."""
    baseline = _baseline()  # каждый bucket total=1000, медиана=1000
    recent = LiquidationBucket(long_volume=Decimal("8000"), short_volume=Decimal("1000"))
    # total=9000, ratio=9x > 5x; long_share=8000/9000≈0.89
    signal = detect_liquidation_sweep(recent, baseline)
    assert signal is not None
    assert signal.action == "BUY"
    assert signal.spike_ratio == Decimal("9")
    assert signal.long_share > Decimal("0.6")


def test_short_cascade_returns_sell() -> None:
    """5x baseline и short-side dominates → SELL."""
    baseline = _baseline()
    recent = LiquidationBucket(long_volume=Decimal("1000"), short_volume=Decimal("8000"))
    signal = detect_liquidation_sweep(recent, baseline)
    assert signal is not None
    assert signal.action == "SELL"


def test_neutral_direction_returns_none() -> None:
    """Spike есть, но 50/50 направление → None."""
    baseline = _baseline()
    recent = LiquidationBucket(long_volume=Decimal("4500"), short_volume=Decimal("4500"))
    signal = detect_liquidation_sweep(recent, baseline)
    assert signal is None


def test_below_spike_threshold_returns_none() -> None:
    """3x baseline < 5x threshold → None."""
    baseline = _baseline()
    recent = LiquidationBucket(long_volume=Decimal("2500"), short_volume=Decimal("500"))
    signal = detect_liquidation_sweep(recent, baseline)
    assert signal is None


def test_short_history_returns_none() -> None:
    baseline = _baseline(n=5)  # < min_history=12
    recent = LiquidationBucket(long_volume=Decimal("10000"), short_volume=Decimal("1000"))
    signal = detect_liquidation_sweep(recent, baseline)
    assert signal is None


def test_low_baseline_skipped() -> None:
    """Если baseline median слишком низкий — noisy pair, skip."""
    baseline = _baseline(long_v="10", short_v="10")  # median = 20 < 100 default
    recent = LiquidationBucket(long_volume=Decimal("1000"), short_volume=Decimal("100"))
    signal = detect_liquidation_sweep(recent, baseline)
    assert signal is None


def test_zero_recent_returns_none() -> None:
    baseline = _baseline()
    recent = LiquidationBucket(long_volume=Decimal("0"), short_volume=Decimal("0"))
    signal = detect_liquidation_sweep(recent, baseline)
    assert signal is None


def test_custom_spike_threshold() -> None:
    """С threshold=2 уже 2x baseline firing."""
    baseline = _baseline()  # median 1000
    recent = LiquidationBucket(long_volume=Decimal("2500"), short_volume=Decimal("100"))
    cfg = LiquidationSweepConfig(spike_threshold=Decimal("2"))
    signal = detect_liquidation_sweep(recent, baseline, cfg)
    assert signal is not None
    assert signal.action == "BUY"


def test_confidence_saturates_at_10x() -> None:
    """20x spike → confidence=1.0 (насыщение)."""
    baseline = _baseline()
    recent = LiquidationBucket(long_volume=Decimal("20000"), short_volume=Decimal("500"))
    signal = detect_liquidation_sweep(recent, baseline)
    assert signal is not None
    assert signal.confidence_raw == 1.0


def test_confidence_proportional_below_10x() -> None:
    """6x spike → confidence=0.6."""
    baseline = _baseline()
    recent = LiquidationBucket(long_volume=Decimal("5500"), short_volume=Decimal("500"))
    # total=6000, ratio=6x → conf=0.6
    signal = detect_liquidation_sweep(recent, baseline)
    assert signal is not None
    assert abs(signal.confidence_raw - 0.6) < 0.001


def test_reason_contains_ratio_and_share() -> None:
    baseline = _baseline()
    recent = LiquidationBucket(long_volume=Decimal("9000"), short_volume=Decimal("500"))
    signal = detect_liquidation_sweep(recent, baseline)
    assert signal is not None
    assert "baseline" in signal.reason
    assert "BUY" in signal.reason or "отскок" in signal.reason


def test_liquidation_bucket_total_property() -> None:
    b = LiquidationBucket(long_volume=Decimal("100"), short_volume=Decimal("50"))
    assert b.total == Decimal("150")
