"""Тесты live Coinglass-провайдеров на fake-клиенте (без сети/ключа)."""

from __future__ import annotations

from decimal import Decimal

from parsers.coinglass.live_providers import (
    CoinglassLiveDeltaProvider,
    CoinglassLiveFundingProvider,
    CoinglassLiveLiquidationProvider,
    CoinglassLiveOpenInterestProvider,
    build_live_providers,
)
from parsers.coinglass.models import CoinglassLiquidationBucket


class _FakeCG:
    def get_funding_history(self, **_: object) -> list[tuple[int, Decimal]]:
        return [(100, Decimal("0.001")), (200, Decimal("0.009"))]

    def get_liquidation_history(self, **_: object) -> list[CoinglassLiquidationBucket]:
        return [
            CoinglassLiquidationBucket(
                timestamp_ms=t,
                long_liquidation_usd=Decimal(v),
                short_liquidation_usd=Decimal("1"),
            )
            for t, v in [(100, "10"), (200, "20"), (300, "999")]
        ]

    def get_open_interest_history(self, **_: object) -> list[tuple[int, Decimal]]:
        return [(100, Decimal("1000")), (200, Decimal("1100")), (300, Decimal("1200"))]

    def get_cvd_history(self, **_: object) -> list[tuple[int, Decimal]]:
        return [(100, Decimal("5")), (200, Decimal("15")), (300, Decimal("25"))]


def _providers() -> tuple[
    CoinglassLiveFundingProvider,
    CoinglassLiveLiquidationProvider,
    CoinglassLiveOpenInterestProvider,
    CoinglassLiveDeltaProvider,
]:
    p = build_live_providers("BTC-USDT", "4h", client=_FakeCG(), refresh_s=0)  # type: ignore[arg-type]
    assert p is not None
    return p


def test_unmapped_symbol_returns_none() -> None:
    assert build_live_providers("ZZZ-USDT", "4h", client=_FakeCG()) is None


def test_funding_anti_lookahead() -> None:
    funding, *_ = _providers()
    assert funding.get_funding_rate("BTC-USDT", 50) is None
    assert funding.get_funding_rate("BTC-USDT", 150) == Decimal("0.001")
    assert funding.get_funding_rate("BTC-USDT", 9999) == Decimal("0.009")


def test_liquidation_bucket_and_baseline() -> None:
    _f, liq, _oi, _d = _providers()
    b = liq.get_bucket("BTC-USDT", 250)
    assert b is not None and b.long_volume == Decimal("20")  # последний ≤250
    base = liq.get_baseline("BTC-USDT", 300, 2)
    # окно до последнего: buckets ts=100,200 (исключая текущий ts=300)
    assert [x.long_volume for x in base] == [Decimal("10"), Decimal("20")]


def test_oi_and_cvd_series_respect_ts_and_n() -> None:
    _f, _l, oi, delta = _providers()
    assert oi.get_series("BTC-USDT", 200, 5) == [Decimal("1000"), Decimal("1100")]
    assert delta.get_cvd_series("BTC-USDT", 300, 2) == [Decimal("15"), Decimal("25")]
