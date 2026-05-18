"""Тесты composite_backtest: чистая логика + wiring с fake-клиентом.

Без сети и без COINGLASS_API_KEY (DI fake client).
"""

from __future__ import annotations

from decimal import Decimal

from parsers.coinglass.models import CoinglassLiquidationBucket
from scripts.composite_backtest import TsFundingProvider, build_providers


def test_ts_funding_provider_anti_lookahead() -> None:
    fp = TsFundingProvider([(300, Decimal("0.03")), (100, Decimal("0.01")), (200, Decimal("0.02"))])
    assert fp.get_funding_rate("X", 50) is None  # до первой записи
    assert fp.get_funding_rate("X", 100) == Decimal("0.01")
    assert fp.get_funding_rate("X", 250) == Decimal("0.02")  # последняя ≤ ts
    assert fp.get_funding_rate("X", 999) == Decimal("0.03")


class _FakeCG:
    """Имитация CoinglassClient (single-shot ветка: interval вне _INTERVAL_MS)."""

    def get_liquidation_history(self, **_: object) -> list[CoinglassLiquidationBucket]:
        return [
            CoinglassLiquidationBucket(
                timestamp_ms=1000,
                long_liquidation_usd=Decimal("500000"),
                short_liquidation_usd=Decimal("1000"),
            )
        ]

    def get_open_interest_history(self, **_: object) -> list[tuple[int, Decimal]]:
        return [(1000, Decimal("1000")), (2000, Decimal("1100"))]

    def get_cvd_history(self, **_: object) -> list[tuple[int, Decimal]]:
        return [(1000, Decimal("10")), (2000, Decimal("20"))]

    def get_funding_history(self, **_: object) -> list[tuple[int, Decimal]]:
        return [(1000, Decimal("0.0001")), (2000, Decimal("0.0009"))]


def test_build_providers_wires_funding_from_fake_client() -> None:
    funding, liq, oi, delta = build_providers(
        "BTC-USDT",
        "7m",  # не в _INTERVAL_MS → single-shot, без пагинации
        start_ms=0,
        end_ms=10_000,
        client=_FakeCG(),  # type: ignore[arg-type]
    )
    assert funding.get_funding_rate("BTC-USDT", 1500) == Decimal("0.0001")
    assert funding.get_funding_rate("BTC-USDT", 5000) == Decimal("0.0009")
    # liq/oi/delta провайдеры построены (не падает на доступе).
    assert liq is not None
    assert oi is not None
    assert delta is not None


def test_build_providers_unmapped_symbol_empty_funding() -> None:
    funding, _liq, _oi, _delta = build_providers(
        "UNKNOWN-USDT",
        "7m",
        start_ms=0,
        end_ms=1,
        client=_FakeCG(),  # type: ignore[arg-type]
    )
    # map_symbol → None ⇒ funding не запрашивается ⇒ пусто (honest gate).
    assert funding.get_funding_rate("UNKNOWN-USDT", 9999) is None
