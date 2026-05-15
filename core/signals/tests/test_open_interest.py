"""Тесты OI-trend детектора (gate методологии Щукина)."""

from __future__ import annotations

from decimal import Decimal

from core.signals import OIState, OpenInterestConfig, detect_oi_trend


def _series(*vals: str) -> list[Decimal]:
    return [Decimal(v) for v in vals]


def test_short_history_returns_none() -> None:
    assert detect_oi_trend(_series("100", "101")) is None


def test_rising_detected() -> None:
    # +10% за 6 срезов → RISING (порог 3%)
    s = detect_oi_trend(_series("100", "100", "102", "104", "106", "108", "110"))
    assert s is not None
    assert s.state == OIState.RISING
    assert s.change_pct == Decimal("10")


def test_falling_detected() -> None:
    s = detect_oi_trend(_series("110", "108", "106", "104", "102", "100", "95"))
    assert s is not None
    assert s.state == OIState.FALLING
    assert s.change_pct < 0


def test_flat_when_change_below_threshold() -> None:
    # ~1% изменение < порог 3% → FLAT
    s = detect_oi_trend(_series("100", "100", "100", "100", "100", "100", "101"))
    assert s is not None
    assert s.state == OIState.FLAT


def test_breakout_from_low_base() -> None:
    """OI стартует у минимума окна, потом резко вверх → breakout."""
    # 24 точки: первые ~у минимума, резкий рост в конце
    base = ["100"] * 18
    ramp = ["103", "107", "112", "118", "125", "133"]  # +33%
    s = detect_oi_trend(
        _series(*base, *ramp),
        OpenInterestConfig(from_low_lookback=24, lookback=6),
    )
    assert s is not None
    assert s.state == OIState.RISING
    assert s.breakout_from_low is True


def test_no_breakout_when_high_base() -> None:
    """OI стартует у максимума окна (не низкая база) → breakout False."""
    high_start = ["130", "128", "120", "110", "100", "100"] + ["100"] * 12
    ramp = ["103", "107", "112", "118", "125", "133"]
    s = detect_oi_trend(
        _series(*high_start, *ramp),
        OpenInterestConfig(from_low_lookback=24, lookback=6),
    )
    assert s is not None
    assert s.state == OIState.RISING
    assert s.breakout_from_low is False


def test_zero_reference_guarded() -> None:
    s = detect_oi_trend(_series("0", "0", "0", "0", "0", "0", "0"))
    assert s is None
