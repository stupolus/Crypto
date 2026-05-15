"""Тесты DI-провайдеров для liquidation_reversal (план 21 фаза 21.1)."""

from __future__ import annotations

from decimal import Decimal

from core.signals import (
    DeltaProvider,
    LiquidationProvider,
    OpenInterestProvider,
    StaticDeltaProvider,
    StaticLiquidationProvider,
    StaticOpenInterestProvider,
)
from core.signals.liquidation_sweep import LiquidationBucket


def _bucket(lng: str, sht: str) -> LiquidationBucket:
    return LiquidationBucket(long_volume=Decimal(lng), short_volume=Decimal(sht))


def test_protocol_compliance() -> None:
    assert isinstance(StaticLiquidationProvider(), LiquidationProvider)
    assert isinstance(StaticOpenInterestProvider(), OpenInterestProvider)
    assert isinstance(StaticDeltaProvider(), DeltaProvider)


def test_liquidation_get_bucket_exact_match() -> None:
    p = StaticLiquidationProvider(
        {"BTC-USDT": {1000: _bucket("50000", "10000"), 2000: _bucket("0", "30000")}}
    )
    b = p.get_bucket("BTC-USDT", 1000)
    assert b is not None
    assert b.long_volume == Decimal("50000")
    assert p.get_bucket("BTC-USDT", 1500) is None  # нет точного ts
    assert p.get_bucket("ETH-USDT", 1000) is None  # нет symbol


def test_liquidation_baseline_strictly_prior() -> None:
    p = StaticLiquidationProvider(
        {
            "BTC-USDT": {
                100: _bucket("1", "1"),
                200: _bucket("2", "2"),
                300: _bucket("3", "3"),
                400: _bucket("4", "4"),
            }
        }
    )
    base = p.get_baseline("BTC-USDT", 400, n=2)
    # СТРОГО до 400 → {100,200,300}, последние 2 → [200, 300]
    assert [b.long_volume for b in base] == [Decimal("2"), Decimal("3")]
    # ts=100 → ничего строго раньше
    assert p.get_baseline("BTC-USDT", 100, n=5) == []


def test_oi_series_up_to_timestamp() -> None:
    p = StaticOpenInterestProvider(
        {
            "BTC-USDT": [
                (100, Decimal("1000")),
                (200, Decimal("1100")),
                (300, Decimal("1200")),
                (400, Decimal("900")),
            ]
        }
    )
    s = p.get_series("BTC-USDT", 300, n=2)
    # ts <= 300 → [1000,1100,1200], последние 2
    assert s == [Decimal("1100"), Decimal("1200")]
    assert p.get_series("BTC-USDT", 50, n=5) == []
    assert p.get_series("ETH-USDT", 300, n=5) == []


def test_oi_series_sorted_on_unsorted_input() -> None:
    p = StaticOpenInterestProvider(
        {"X-USDT": [(300, Decimal("3")), (100, Decimal("1")), (200, Decimal("2"))]}
    )
    assert p.get_series("X-USDT", 999, n=3) == [Decimal("1"), Decimal("2"), Decimal("3")]


def test_delta_cvd_series() -> None:
    p = StaticDeltaProvider(
        {"BTC-USDT": [(100, Decimal("-5")), (200, Decimal("3")), (300, Decimal("8"))]}
    )
    assert p.get_cvd_series("BTC-USDT", 250, n=5) == [Decimal("-5"), Decimal("3")]
    assert p.get_cvd_series("BTC-USDT", 300, n=1) == [Decimal("8")]


def test_empty_providers_safe() -> None:
    assert StaticLiquidationProvider().get_bucket("X", 1) is None
    assert StaticLiquidationProvider().get_baseline("X", 1, 5) == []
    assert StaticOpenInterestProvider().get_series("X", 1, 5) == []
    assert StaticDeltaProvider().get_cvd_series("X", 1, 5) == []
