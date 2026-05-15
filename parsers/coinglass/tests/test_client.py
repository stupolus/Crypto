"""Тесты CoinglassClient (respx mock, без сети). План 21 фаза 21.4."""

from __future__ import annotations

from decimal import Decimal

import httpx
import respx

from parsers.coinglass.client import CoinglassClient

_BASE = "https://open-api-v4.coinglass.com"


def _client(key: str | None = "k") -> CoinglassClient:
    return CoinglassClient(api_key=key, client=httpx.Client(base_url=_BASE))


def test_not_configured_returns_empty() -> None:
    c = CoinglassClient(api_key=None, client=httpx.Client(base_url=_BASE))
    assert c.configured is False
    assert c.get_liquidation_history(exchange="Binance", symbol="BTCUSDT", interval="1h") == []


@respx.mock
def test_liquidation_history_parsed() -> None:
    respx.get(f"{_BASE}/api/futures/liquidation/history").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "0",
                "msg": "success",
                "data": [
                    {
                        "time": 1700000000000,
                        "long_liquidation_usd": "12345.6",
                        "short_liquidation_usd": "0",
                    },
                    {
                        "time": 1700003600000,
                        "long_liquidation_usd": "0",
                        "short_liquidation_usd": "98765",
                    },
                ],
            },
        )
    )
    rows = _client().get_liquidation_history(
        exchange="Binance", symbol="BTCUSDT", interval="1h", limit=2
    )
    assert len(rows) == 2
    assert rows[0].timestamp_ms == 1700000000000
    assert rows[0].long_liquidation_usd == Decimal("12345.6")
    assert rows[1].short_liquidation_usd == Decimal("98765")


@respx.mock
def test_plan_inactive_returns_empty() -> None:
    respx.get(f"{_BASE}/api/futures/liquidation/history").mock(
        return_value=httpx.Response(200, json={"code": "401", "msg": "Upgrade plan"})
    )
    rows = _client().get_liquidation_history(exchange="Binance", symbol="BTCUSDT", interval="1h")
    assert rows == []  # graceful, без исключения


@respx.mock
def test_network_error_returns_empty() -> None:
    respx.get(f"{_BASE}/api/futures/liquidation/history").mock(
        side_effect=httpx.ConnectError("boom")
    )
    assert (
        _client().get_liquidation_history(exchange="Binance", symbol="BTCUSDT", interval="1h") == []
    )


@respx.mock
def test_oi_history_parsed_tolerant_fields() -> None:
    respx.get(f"{_BASE}/api/futures/open-interest/aggregated-history").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "0",
                "msg": "success",
                "data": [
                    {"time": 1700000000000, "close": "5000000"},
                    {"time": 1700003600000, "openInterest": "5100000"},
                ],
            },
        )
    )
    oi = _client().get_open_interest_history(symbol="BTC", interval="1h", limit=2)
    assert oi == [
        (1700000000000, Decimal("5000000")),
        (1700003600000, Decimal("5100000")),
    ]


@respx.mock
def test_auth_header_sent() -> None:
    route = respx.get(f"{_BASE}/api/futures/liquidation/history").mock(
        return_value=httpx.Response(200, json={"code": "0", "data": []})
    )
    _client(key="secret123").get_liquidation_history(
        exchange="Binance", symbol="BTCUSDT", interval="1h"
    )
    assert route.calls[0].request.headers["CG-API-KEY"] == "secret123"
