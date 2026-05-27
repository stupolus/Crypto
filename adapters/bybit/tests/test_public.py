"""Tests for adapters.bybit.public (V5 read-only)."""

from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
import respx

from adapters.bybit.public import (
    BybitAPIError,
    BybitPublicAPI,
)
from adapters.bybit.settings import BybitSettings

_BASE = "https://api.bybit.com"


def _client(api_key: str | None = None) -> BybitPublicAPI:
    settings = BybitSettings(env="mainnet", api_key=api_key, api_secret=None)
    return BybitPublicAPI(settings=settings)


@pytest.mark.asyncio
@respx.mock
async def test_server_time_ms_from_nano() -> None:
    respx.get(f"{_BASE}/v5/market/time").mock(
        return_value=httpx.Response(
            200,
            json={
                "retCode": 0,
                "retMsg": "OK",
                "result": {"timeSecond": "1700000000", "timeNano": "1700000000123456789"},
            },
        )
    )
    api = _client()
    ms = await api.server_time_ms()
    await api.aclose()
    assert ms == 1_700_000_000_123  # 1.7e18 ns // 1e6


@pytest.mark.asyncio
@respx.mock
async def test_server_time_ms_falls_back_to_seconds() -> None:
    respx.get(f"{_BASE}/v5/market/time").mock(
        return_value=httpx.Response(
            200, json={"retCode": 0, "result": {"timeSecond": "1700000000"}}
        )
    )
    api = _client()
    ms = await api.server_time_ms()
    await api.aclose()
    assert ms == 1_700_000_000_000


@pytest.mark.asyncio
@respx.mock
async def test_get_klines_parses_and_sorts_asc() -> None:
    # Bybit отдаёт NEWEST first; адаптер обязан вернуть ASC.
    respx.get(f"{_BASE}/v5/market/kline").mock(
        return_value=httpx.Response(
            200,
            json={
                "retCode": 0,
                "result": {
                    "list": [
                        ["1700000300000", "100", "101", "99", "100.5", "10", "1005"],
                        ["1700000000000", "99", "100", "98", "99.5", "20", "1990"],
                    ]
                },
            },
        )
    )
    api = _client()
    klines = await api.get_klines("BTCUSDT", "15m", limit=10)
    await api.aclose()
    assert len(klines) == 2
    assert klines[0].start_time_ms == 1_700_000_000_000
    assert klines[1].start_time_ms == 1_700_000_300_000
    assert klines[0].close == Decimal("99.5")


@pytest.mark.asyncio
@respx.mock
async def test_get_klines_rejects_unknown_timeframe() -> None:
    api = _client()
    with pytest.raises(ValueError, match="unsupported timeframe"):
        await api.get_klines("BTCUSDT", "7m")
    await api.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_get_open_interest_history_parses_and_sorts() -> None:
    respx.get(f"{_BASE}/v5/market/open-interest").mock(
        return_value=httpx.Response(
            200,
            json={
                "retCode": 0,
                "result": {
                    "list": [
                        {"timestamp": "1700000300000", "openInterest": "5001.5"},
                        {"timestamp": "1700000000000", "openInterest": "5000.0"},
                    ]
                },
            },
        )
    )
    api = _client()
    oi = await api.get_open_interest_history("BTCUSDT", "15m", limit=10)
    await api.aclose()
    assert [s.timestamp_ms for s in oi] == [1_700_000_000_000, 1_700_000_300_000]
    assert oi[1].open_interest == Decimal("5001.5")


@pytest.mark.asyncio
@respx.mock
async def test_get_funding_history_parses() -> None:
    respx.get(f"{_BASE}/v5/market/funding/history").mock(
        return_value=httpx.Response(
            200,
            json={
                "retCode": 0,
                "result": {
                    "list": [
                        {
                            "symbol": "BTCUSDT",
                            "fundingRate": "0.0001",
                            "fundingRateTimestamp": "1700000000000",
                        },
                    ]
                },
            },
        )
    )
    api = _client()
    fr = await api.get_funding_history("BTCUSDT", limit=10)
    await api.aclose()
    assert len(fr) == 1
    assert fr[0].funding_rate == Decimal("0.0001")


@pytest.mark.asyncio
@respx.mock
async def test_api_error_raises_bybitapierror() -> None:
    respx.get(f"{_BASE}/v5/market/kline").mock(
        return_value=httpx.Response(200, json={"retCode": 10001, "retMsg": "param error"})
    )
    api = _client()
    with pytest.raises(BybitAPIError) as exc:
        await api.get_klines("BTCUSDT", "15m")
    await api.aclose()
    assert exc.value.code == 10001
    assert "param error" in str(exc.value)


@pytest.mark.asyncio
@respx.mock
async def test_optional_api_key_sent_in_header() -> None:
    route = respx.get(f"{_BASE}/v5/market/time").mock(
        return_value=httpx.Response(200, json={"retCode": 0, "result": {"timeSecond": "1"}})
    )
    api = _client(api_key="my-key")
    await api.server_time_ms()
    await api.aclose()
    assert route.calls.last.request.headers.get("X-BAPI-API-KEY") == "my-key"


def test_settings_base_url_per_env() -> None:
    assert BybitSettings(env="mainnet").base_url == "https://api.bybit.com"
    assert BybitSettings(env="demo").base_url == "https://api-demo.bybit.com"
    assert BybitSettings(env="testnet").base_url == "https://api-testnet.bybit.com"


def test_module_has_no_trading_methods() -> None:
    """Жёсткая страховка: в public-модуле НЕТ trading-методов."""
    forbidden = {"place_order", "cancel_order", "place_active_order", "submit_order"}
    methods = {m for m in dir(BybitPublicAPI) if not m.startswith("_")}
    assert forbidden.isdisjoint(methods), (
        f"public-only API не должен иметь trading-методов: {forbidden & methods}"
    )
