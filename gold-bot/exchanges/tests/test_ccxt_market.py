"""Тесты market-data слоя адаптеров (ccxt замокан, без сети)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from exchanges.bingx import BingXAdapter
from exchanges.bybit import BybitAdapter
from exchanges.ccxt_base import CcxtAdapter


def _adapter(client: Any) -> CcxtAdapter:
    return CcxtAdapter(client)


@pytest.mark.asyncio
async def test_fetch_markets_sorted() -> None:
    client = AsyncMock()
    client.load_markets.return_value = {"ETH/USDT:USDT": {}, "BTC/USDT:USDT": {}}
    assert await _adapter(client).fetch_markets() == ["BTC/USDT:USDT", "ETH/USDT:USDT"]


@pytest.mark.asyncio
async def test_fetch_ohlcv_maps() -> None:
    client = AsyncMock()
    client.fetch_ohlcv.return_value = [
        [1000, 1.0, 2.0, 0.5, 1.5, 100.0],
        [2000, 1.5, 2.5, 1.0, 2.0, 200.0],
    ]
    candles = await _adapter(client).fetch_ohlcv("BTC-USDT", "15m")
    assert len(candles) == 2
    assert candles[0].timestamp == 1000
    assert candles[0].open == Decimal("1.0")
    assert candles[1].close == Decimal("2.0")
    # символ нормализован перед вызовом ccxt
    client.fetch_ohlcv.assert_awaited_once_with("BTC/USDT:USDT", "15m", None, None)


@pytest.mark.asyncio
async def test_fetch_ticker_maps_and_spread() -> None:
    client = AsyncMock()
    client.fetch_ticker.return_value = {
        "last": 100.0,
        "bid": 99.0,
        "ask": 101.0,
        "quoteVolume": 1_000_000.0,
        "timestamp": 12345,
    }
    t = await _adapter(client).fetch_ticker("BTCUSDT")
    assert t.symbol == "BTC/USDT:USDT"
    assert t.last == Decimal("100.0")
    assert t.spread == Decimal("2.0")


@pytest.mark.asyncio
async def test_fetch_ticker_missing_volume_is_zero() -> None:
    client = AsyncMock()
    client.fetch_ticker.return_value = {
        "last": 100.0,
        "bid": 99.0,
        "ask": 101.0,
        "quoteVolume": None,
        "timestamp": None,
    }
    t = await _adapter(client).fetch_ticker("BTC/USDT:USDT")
    assert t.quote_volume_24h == Decimal("0")
    assert t.timestamp == 0


@pytest.mark.asyncio
async def test_fetch_order_book_maps() -> None:
    client = AsyncMock()
    client.fetch_order_book.return_value = {
        "bids": [[99.0, 1.0], [98.0, 2.0]],
        "asks": [[101.0, 1.5]],
    }
    bids, asks = await _adapter(client).fetch_order_book("BTC-USDT", depth=5)
    assert bids[0] == (Decimal("99.0"), Decimal("1.0"))
    assert asks[0] == (Decimal("101.0"), Decimal("1.5"))
    client.fetch_order_book.assert_awaited_once_with("BTC/USDT:USDT", 5)


@pytest.mark.asyncio
async def test_fetch_funding_rate_maps() -> None:
    client = AsyncMock()
    client.fetch_funding_rate.return_value = {
        "fundingRate": 0.0001,
        "fundingTimestamp": 1700000000000,
    }
    rate, next_ts = await _adapter(client).fetch_funding_rate("BTC-USDT")
    assert rate == Decimal("0.0001")
    assert next_ts == 1700000000000


@pytest.mark.asyncio
async def test_funding_rate_falls_back_to_next_funding_time() -> None:
    client = AsyncMock()
    client.fetch_funding_rate.return_value = {
        "fundingRate": None,
        "fundingTimestamp": None,
        "nextFundingTime": 1700000000001,
    }
    rate, next_ts = await _adapter(client).fetch_funding_rate("BTC-USDT")
    assert rate == Decimal("0")
    assert next_ts == 1700000000001


@pytest.mark.asyncio
async def test_close_delegates() -> None:
    client = AsyncMock()
    await _adapter(client).close()
    client.close.assert_awaited_once()


def test_bingx_adapter_name_and_injected_client() -> None:
    client = AsyncMock()
    adapter = BingXAdapter(client=client)
    assert adapter.name == "bingx"
    assert adapter.client is client


def test_bybit_adapter_name_and_injected_client() -> None:
    client = AsyncMock()
    adapter = BybitAdapter(client=client)
    assert adapter.name == "bybit"
    assert adapter.client is client
