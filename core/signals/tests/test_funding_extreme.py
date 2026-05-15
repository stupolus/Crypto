"""Unit-тесты ``detect_funding_extreme``."""

from __future__ import annotations

from decimal import Decimal

from core.signals.funding_extreme import (
    FundingExtremeConfig,
    detect_funding_extreme,
)


def _build_history(values: list[str]) -> list[Decimal]:
    return [Decimal(v) for v in values]


def test_extreme_positive_funding_returns_sell() -> None:
    # 30 значений от 0.0001 до 0.0003 (нормальный funding)
    history = _build_history([f"0.000{1 + i % 3}" for i in range(30)])
    # Current = 0.001 (≈ в 3 раза больше любого в history) → 95%+ перцентиль
    signal = detect_funding_extreme(Decimal("0.001"), history)
    assert signal is not None
    assert signal.action == "SELL"
    assert signal.funding_rate == Decimal("0.001")
    assert signal.percentile >= Decimal("0.95")
    assert signal.confidence_raw > 0.5


def test_extreme_negative_funding_returns_buy() -> None:
    history = _build_history([f"0.000{1 + i % 3}" for i in range(30)])
    # Current = -0.001 → ниже 5% перцентиля
    signal = detect_funding_extreme(Decimal("-0.001"), history)
    assert signal is not None
    assert signal.action == "BUY"
    assert signal.percentile <= Decimal("0.05")


def test_neutral_funding_returns_none() -> None:
    # History 0..29, current = 15 (медиана)
    history = [Decimal(i) / Decimal("10000") for i in range(30)]
    signal = detect_funding_extreme(Decimal("0.0015"), history)
    assert signal is None


def test_short_history_returns_none() -> None:
    """Если истории мало (< min_history) — детектор молчит."""
    history = _build_history(["0.0001", "0.0002", "0.0003"])
    signal = detect_funding_extreme(Decimal("0.01"), history)
    assert signal is None


def test_custom_min_history() -> None:
    """С min_history=2 две записи достаточно."""
    history = _build_history(["0.0001", "0.0002"])
    cfg = FundingExtremeConfig(min_history=2)
    signal = detect_funding_extreme(Decimal("0.01"), history, cfg)
    assert signal is not None
    assert signal.action == "SELL"


def test_custom_percentile_thresholds() -> None:
    """С более agressive thresholds сигналы появляются чаще."""
    history = [Decimal(i) / Decimal("10000") for i in range(30)]
    # Current = 0.0005 → ≤ 6 значений из 30 → percentile ≈ 0.2
    cfg = FundingExtremeConfig(
        percentile_high=Decimal("0.55"),
        percentile_low=Decimal("0.45"),
    )
    signal = detect_funding_extreme(Decimal("0.0005"), history, cfg)
    # При threshold 0.45 percentile 0.2 < 0.45 → BUY
    assert signal is not None
    assert signal.action == "BUY"


def test_confidence_at_extreme_is_high() -> None:
    """Перцентиль 1.0 → confidence ≈ 1.0."""
    history = [Decimal("0.0001")] * 30
    signal = detect_funding_extreme(Decimal("0.005"), history)
    assert signal is not None
    # confidence = |1.0 - 0.5| * 2 = 1.0
    assert signal.confidence_raw == 1.0


def test_signal_reason_contains_funding_and_percentile() -> None:
    history = _build_history([f"0.000{1 + i % 3}" for i in range(30)])
    signal = detect_funding_extreme(Decimal("0.001"), history)
    assert signal is not None
    assert "funding" in signal.reason
    assert "0.001" in signal.reason


def test_zero_funding_with_positive_history_returns_buy() -> None:
    """Если history вся positive (longs всегда платили), а current = 0 → contrarian."""
    history = [Decimal("0.0001") * Decimal(i + 1) for i in range(30)]
    # Current = 0 — ниже всех → percentile = 0
    signal = detect_funding_extreme(Decimal("0"), history)
    assert signal is not None
    assert signal.action == "BUY"
    assert signal.percentile <= Decimal("0.05")
