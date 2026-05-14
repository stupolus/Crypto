"""Unit-тесты ``detect_order_flow``."""

from __future__ import annotations

from decimal import Decimal

from core.signals.order_flow import (
    OrderFlowConfig,
    compute_imbalance,
    detect_order_flow,
)


def test_compute_imbalance_balanced_zero() -> None:
    assert compute_imbalance(Decimal("100"), Decimal("100")) == Decimal("0")


def test_compute_imbalance_all_bids() -> None:
    assert compute_imbalance(Decimal("100"), Decimal("0")) == Decimal("1")


def test_compute_imbalance_all_asks() -> None:
    assert compute_imbalance(Decimal("0"), Decimal("100")) == Decimal("-1")


def test_compute_imbalance_partial() -> None:
    """75% bids / 25% asks → imbalance = 0.5."""
    result = compute_imbalance(Decimal("75"), Decimal("25"))
    assert result == Decimal("0.5")


def test_compute_imbalance_zero_total_returns_zero() -> None:
    assert compute_imbalance(Decimal("0"), Decimal("0")) == Decimal("0")


def test_detect_buy_pressure() -> None:
    """80/20 → imbalance=0.6, выше threshold 0.6? Точно равно — НЕ firing."""
    # 0.6 equal → not firing (cfg.threshold = 0.6 строгое >)
    signal = detect_order_flow(Decimal("80"), Decimal("20"))
    assert signal is None  # ровно threshold


def test_detect_buy_pressure_above_threshold() -> None:
    """85/15 → imbalance=0.7, выше threshold 0.6 → BUY."""
    signal = detect_order_flow(Decimal("85"), Decimal("15"))
    assert signal is not None
    assert signal.action == "BUY"
    assert signal.imbalance == Decimal("0.7")
    assert signal.confidence_raw == 0.7


def test_detect_sell_pressure() -> None:
    """15/85 → imbalance=-0.7 → SELL."""
    signal = detect_order_flow(Decimal("15"), Decimal("85"))
    assert signal is not None
    assert signal.action == "SELL"
    assert signal.imbalance == Decimal("-0.7")
    assert signal.confidence_raw == 0.7


def test_detect_neutral_returns_none() -> None:
    signal = detect_order_flow(Decimal("50"), Decimal("50"))
    assert signal is None


def test_detect_custom_threshold() -> None:
    """С threshold=0.3 уже 70/30 firing."""
    cfg = OrderFlowConfig(threshold=Decimal("0.3"))
    signal = detect_order_flow(Decimal("70"), Decimal("30"), cfg)
    assert signal is not None
    assert signal.action == "BUY"
    assert signal.imbalance == Decimal("0.4")


def test_detect_negative_volume_returns_none() -> None:
    """Защита от некорректного input."""
    signal = detect_order_flow(Decimal("-10"), Decimal("100"))
    assert signal is None


def test_detect_zero_volume_returns_none() -> None:
    """Нулевой total → imbalance=0 → не firing."""
    signal = detect_order_flow(Decimal("0"), Decimal("0"))
    assert signal is None


def test_reason_string_contains_imbalance() -> None:
    signal = detect_order_flow(Decimal("90"), Decimal("10"))
    assert signal is not None
    assert "imbalance" in signal.reason
    # 90/100 - 10/100 = 0.8
    assert "0.800" in signal.reason


def test_full_buy_pressure() -> None:
    """100% bids, 0% asks → imbalance=1.0, confidence=1.0."""
    signal = detect_order_flow(Decimal("100"), Decimal("0"))
    assert signal is not None
    assert signal.action == "BUY"
    assert signal.imbalance == Decimal("1")
    assert signal.confidence_raw == 1.0


def test_full_sell_pressure() -> None:
    signal = detect_order_flow(Decimal("0"), Decimal("100"))
    assert signal is not None
    assert signal.action == "SELL"
    assert signal.imbalance == Decimal("-1")
