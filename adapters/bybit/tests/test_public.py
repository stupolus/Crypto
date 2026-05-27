"""Тесты PublicAPI Bybit V5: klines (ASC), ticker — через respx-моки."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from adapters.bybit.client import BybitClient
from adapters.bybit.public import PublicAPI
from adapters.bybit.settings import BybitSettings

_TESTNET_URL = "https://api-testnet.bybit.com"


def _kline_envelope(rows: list[list[str]]) -> dict[str, Any]:
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {"category": "linear", "symbol": "BTCUSDT", "list": rows},
        "retExtInfo": {},
        "time": 1700000000000,
    }


def _ticker_envelope(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": {"category": "linear", "list": items},
        "retExtInfo": {},
        "time": 1700000000000,
    }


@pytest.mark.asyncio
async def test_get_kline_returns_asc_klines() -> None:
    """Bybit отдаёт DESC, мы переворачиваем в ASC."""
    settings = BybitSettings(_env_file=None, env="testnet")
    # Bybit-формат: [start_ms, o, h, l, c, v, turnover] — DESC.
    rows = [
        ["1700000120000", "100", "110", "95", "105", "10", "1050"],
        ["1700000060000", "98", "102", "97", "100", "8", "800"],
        ["1700000000000", "95", "99", "94", "98", "12", "1176"],
    ]
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        route = mock.get("/v5/market/kline").mock(
            return_value=httpx.Response(200, json=_kline_envelope(rows))
        )
        async with BybitClient(settings=settings) as c:
            klines = await PublicAPI(c).get_kline("BTC-USDT", interval="1", limit=3)
        # Проверим параметры запроса.
        last_request = route.calls.last.request
        assert "category=linear" in str(last_request.url)
        assert "symbol=BTCUSDT" in str(last_request.url)  # из проектного формата
        assert "interval=1" in str(last_request.url)

    assert [k.start_ms for k in klines] == [
        1700000000000,
        1700000060000,
        1700000120000,
    ]
    # Цены сохранены как Decimal с точным представлением.
    assert klines[0].open == Decimal("95")
    assert klines[-1].close == Decimal("105")


@pytest.mark.asyncio
async def test_get_kline_with_start_end() -> None:
    """start/end передаются в querystring если заданы."""
    settings = BybitSettings(_env_file=None, env="testnet")
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        route = mock.get("/v5/market/kline").mock(
            return_value=httpx.Response(200, json=_kline_envelope([]))
        )
        async with BybitClient(settings=settings) as c:
            await PublicAPI(c).get_kline("BTC-USDT", interval="60", start_ms=1, end_ms=2)
        url_str = str(route.calls.last.request.url)
    assert "start=1" in url_str
    assert "end=2" in url_str


@pytest.mark.asyncio
async def test_get_ticker_returns_project_symbol() -> None:
    """Bybit отдаёт ``BTCUSDT``; мы возвращаем ``BTC-USDT``."""
    settings = BybitSettings(_env_file=None, env="testnet")
    payload = [
        {
            "symbol": "BTCUSDT",
            "lastPrice": "30000.5",
            "markPrice": "30001.0",
            "indexPrice": "30000.0",
            "fundingRate": "0.0001",
            "openInterest": "12345",
        }
    ]
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.get("/v5/market/tickers").mock(
            return_value=httpx.Response(200, json=_ticker_envelope(payload))
        )
        async with BybitClient(settings=settings) as c:
            t = await PublicAPI(c).get_ticker("BTC-USDT")
    assert t.symbol == "BTC-USDT"  # обратная конвертация
    assert t.last_price == Decimal("30000.5")
    assert t.funding_rate == Decimal("0.0001")


@pytest.mark.asyncio
async def test_get_ticker_empty_list_raises() -> None:
    settings = BybitSettings(_env_file=None, env="testnet")
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.get("/v5/market/tickers").mock(
            return_value=httpx.Response(200, json=_ticker_envelope([]))
        )
        async with BybitClient(settings=settings) as c:
            with pytest.raises(ValueError, match="ticker list empty"):
                await PublicAPI(c).get_ticker("BTC-USDT")
