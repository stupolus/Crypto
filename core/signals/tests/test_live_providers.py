"""Тесты live OI-провайдера (план 21 фаза 21.3)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from core.signals import (
    OpenInterestProvider,
    RollingOpenInterestProvider,
    poll_open_interest,
)


def test_protocol_compliance() -> None:
    assert isinstance(RollingOpenInterestProvider(), OpenInterestProvider)


def test_record_and_get_series() -> None:
    p = RollingOpenInterestProvider()
    p.record("BTC-USDT", 100, Decimal("1000"))
    p.record("BTC-USDT", 200, Decimal("1100"))
    p.record("BTC-USDT", 300, Decimal("1200"))
    assert p.get_series("BTC-USDT", 250, n=5) == [Decimal("1000"), Decimal("1100")]
    assert p.get_series("BTC-USDT", 300, n=2) == [Decimal("1100"), Decimal("1200")]
    assert p.get_series("ETH-USDT", 300, n=5) == []


def test_duplicate_ts_ignored() -> None:
    p = RollingOpenInterestProvider()
    p.record("X", 100, Decimal("1"))
    p.record("X", 100, Decimal("999"))  # тот же ts → игнор
    assert p.get_series("X", 100, n=5) == [Decimal("1")]


def test_maxlen_bounds_memory() -> None:
    p = RollingOpenInterestProvider(maxlen=3)
    for i in range(10):
        p.record("X", i, Decimal(str(i)))
    s = p.get_series("X", 99, n=10)
    assert s == [Decimal("7"), Decimal("8"), Decimal("9")]  # только последние 3


@pytest.mark.asyncio
async def test_poll_open_interest_records() -> None:
    p = RollingOpenInterestProvider()
    api = AsyncMock()
    api.get_open_interest.return_value = type(
        "OI", (), {"time_ms": 1234, "open_interest": Decimal("555.5")}
    )()
    ok = await poll_open_interest(api, "BTC-USDT", p)
    assert ok is True
    assert p.get_series("BTC-USDT", 9999, n=1) == [Decimal("555.5")]


@pytest.mark.asyncio
async def test_poll_open_interest_swallows_errors() -> None:
    p = RollingOpenInterestProvider()
    api = AsyncMock()
    api.get_open_interest.side_effect = RuntimeError("network")
    ok = await poll_open_interest(api, "BTC-USDT", p)
    assert ok is False
    assert p.get_series("BTC-USDT", 9999, n=1) == []


# ── Coinglass live-провайдеры (Ф1.2-live) ──────────────────────────────


class _StubClient:
    def __init__(self, **rows: object) -> None:
        self._rows = rows
        self.calls: dict[str, int] = {}

    def _ret(self, key: str) -> object:
        self.calls[key] = self.calls.get(key, 0) + 1
        return self._rows.get(key, [])

    def get_liquidation_history(self, **_kw: object) -> object:
        return self._ret("liq")

    def get_open_interest_history(self, **_kw: object) -> object:
        return self._ret("oi")

    def get_cvd_history(self, **_kw: object) -> object:
        return self._ret("cvd")

    def get_funding_history(self, **_kw: object) -> object:
        return self._ret("fund")


def _liq_row(ts: int, lng: str, sht: str) -> object:
    return type(
        "R",
        (),
        {
            "timestamp_ms": ts,
            "long_liquidation_usd": Decimal(lng),
            "short_liquidation_usd": Decimal(sht),
        },
    )()


def test_coinglass_live_liquidation_provider() -> None:
    from core.signals.live_providers import CoinglassLiveLiquidationProvider

    rows = [_liq_row(100, "1000", "50"), _liq_row(200, "2000", "100")]
    client = _StubClient(liq=rows)
    p = CoinglassLiveLiquidationProvider(
        client,
        bingx_symbol="BTC-USDT",
        cg_symbol="BTCUSDT",
        exchange="Binance",
        interval="4h",
        min_refresh_seconds=999,
    )
    b = p.get_bucket("BTC-USDT", 200)
    assert b is not None and b.long_volume == Decimal("2000")
    baseline = p.get_baseline("BTC-USDT", 200, 5)
    assert [bb.long_volume for bb in baseline] == [Decimal("1000")]
    # неизвестный символ
    assert p.get_bucket("ETH-USDT", 200) is None
    assert p.get_baseline("ETH-USDT", 200, 5) == []
    # throttle: повторный вызов не должен снова дёргать клиента
    p.get_bucket("BTC-USDT", 200)
    assert client.calls["liq"] == 1


def test_coinglass_live_oi_provider() -> None:
    from core.signals.live_providers import CoinglassLiveOpenInterestProvider

    rows = [(100, Decimal("10")), (200, Decimal("11")), (300, Decimal("12"))]
    client = _StubClient(oi=rows)
    p = CoinglassLiveOpenInterestProvider(
        client,
        bingx_symbol="BTC-USDT",
        cg_symbol="BTCUSDT",
        exchange="Binance",
        interval="4h",
        min_refresh_seconds=999,
    )
    assert p.get_series("BTC-USDT", 250, 5) == [Decimal("10"), Decimal("11")]
    assert p.get_series("ETH-USDT", 250, 5) == []


def test_coinglass_live_cvd_provider() -> None:
    from core.signals.live_providers import CoinglassLiveDeltaProvider

    rows = [(100, Decimal("5")), (200, Decimal("-3"))]
    client = _StubClient(cvd=rows)
    p = CoinglassLiveDeltaProvider(
        client,
        bingx_symbol="BTC-USDT",
        cg_symbol="BTCUSDT",
        exchange="Binance",
        interval="4h",
        min_refresh_seconds=999,
    )
    assert p.get_cvd_series("BTC-USDT", 999, 5) == [Decimal("5"), Decimal("-3")]
    assert p.get_cvd_series("ETH-USDT", 999, 5) == []


def test_coinglass_live_funding_provider_latest_value() -> None:
    from core.signals.live_providers import CoinglassLiveFundingProvider

    rows = [(100, Decimal("0.0001")), (200, Decimal("-0.0005"))]
    client = _StubClient(fund=rows)
    p = CoinglassLiveFundingProvider(
        client,
        bingx_symbol="BTC-USDT",
        cg_symbol="BTCUSDT",
        exchange="Binance",
        min_refresh_seconds=999,
    )
    assert p.get_funding_rate("BTC-USDT", 250) == Decimal("-0.0005")
    assert p.get_funding_rate("BTC-USDT", 50) is None  # нет данных до 50
    assert p.get_funding_rate("ETH-USDT", 250) is None


def test_build_coinglass_live_providers_unknown_symbol() -> None:
    from core.signals.live_providers import build_coinglass_live_providers

    client = _StubClient()
    # символ, которого нет в _SYMBOL_MAP, → None
    assert build_coinglass_live_providers(client, "NONEXIST-USDT", "4h") is None


def test_build_coinglass_live_providers_btc_returns_four() -> None:
    from core.signals.live_providers import build_coinglass_live_providers

    client = _StubClient()
    out = build_coinglass_live_providers(client, "BTC-USDT", "4h")
    assert out is not None
    assert len(out) == 4
    liq, oi, delta, funding = out
    # протокольная совместимость
    from core.signals import DeltaProvider, LiquidationProvider, OpenInterestProvider
    from core.signals.composite import FundingProvider

    assert isinstance(liq, LiquidationProvider)
    assert isinstance(oi, OpenInterestProvider)
    assert isinstance(delta, DeltaProvider)
    assert isinstance(funding, FundingProvider)
