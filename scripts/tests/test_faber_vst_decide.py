"""Тест критического пути faber_vst_executor.decide (без сети)."""

from __future__ import annotations

from decimal import Decimal

from scripts.faber_vst_executor import decide


def test_cash_flat_noop() -> None:
    assert decide("CASH", Decimal("0"), Decimal("0")) == "noop"


def test_cash_with_position_closes() -> None:
    assert decide("CASH", Decimal("5"), Decimal("0")) == "close"


def test_long_from_flat_opens() -> None:
    assert decide("LONG", Decimal("0"), Decimal("3")) == "open_long"
    assert decide("LONG", Decimal("-2"), Decimal("3")) == "open_long"


def test_long_within_tolerance_noop() -> None:
    # |3.1 - 3| / 3 = 3.3% < 15% → уже в target
    assert decide("LONG", Decimal("3.1"), Decimal("3")) == "noop"


def test_long_out_of_tolerance_rebalance() -> None:
    # |6 - 3| / 3 = 100% → ребаланс
    assert decide("LONG", Decimal("6"), Decimal("3")) == "rebalance"
