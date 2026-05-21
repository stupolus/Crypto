"""Тесты trading-слоя адаптера (ccxt замокан, без сети)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from exchanges.ccxt_base import CcxtAdapter
from exchanges.errors import InvalidOrder
from exchanges.models import OrderRequest, OrderSide, OrderStatus, OrderType


@pytest.mark.asyncio
async def test_place_market_order_attaches_stop() -> None:
    client = AsyncMock()
    client.create_order.return_value = {
        "id": "ord-1",
        "symbol": "BTC/USDT:USDT",
        "status": "open",
        "filled": 0.0,
    }
    req = OrderRequest(
        symbol="BTC-USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
        stop_price=Decimal("95"),
    )
    result = await CcxtAdapter(client).place_order(req)
    assert result.order_id == "ord-1"
    assert result.status is OrderStatus.OPEN

    args, _ = client.create_order.await_args
    symbol, otype, side, amount, price, params = args
    assert symbol == "BTC/USDT:USDT"
    assert otype == "market"
    assert side == "buy"
    assert amount == 0.1
    assert price is None
    # стоп физически уходит в параметрах ордера
    assert params["stopLossPrice"] == 95.0


@pytest.mark.asyncio
async def test_place_limit_order_passes_price_and_coid() -> None:
    client = AsyncMock()
    client.create_order.return_value = {"id": "x", "symbol": "BTC/USDT:USDT", "status": "open"}
    req = OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.2"),
        price=Decimal("100"),
        stop_price=Decimal("105"),
        client_order_id="my-id",
    )
    await CcxtAdapter(client).place_order(req)
    args, _ = client.create_order.await_args
    _, otype, side, _amount, price, params = args
    assert otype == "limit"
    assert side == "sell"
    assert price == 100.0
    assert params["stopLossPrice"] == 105.0
    assert params["clientOrderId"] == "my-id"


@pytest.mark.asyncio
async def test_cancel_order_delegates_normalized() -> None:
    client = AsyncMock()
    await CcxtAdapter(client).cancel_order("ord-1", "BTC-USDT")
    client.cancel_order.assert_awaited_once_with("ord-1", "BTC/USDT:USDT")


@pytest.mark.asyncio
async def test_cancel_all_orders_delegates() -> None:
    client = AsyncMock()
    await CcxtAdapter(client).cancel_all_orders("BTC-USDT")
    client.cancel_all_orders.assert_awaited_once_with("BTC/USDT:USDT")


@pytest.mark.asyncio
async def test_close_long_position_sends_reduce_only_sell() -> None:
    client = AsyncMock()
    client.fetch_positions.return_value = [
        {"symbol": "BTC/USDT:USDT", "side": "long", "contracts": 0.5}
    ]
    client.create_order.return_value = {
        "id": "close-1",
        "symbol": "BTC/USDT:USDT",
        "status": "closed",
        "filled": 0.5,
    }
    result = await CcxtAdapter(client).close_position("BTC-USDT")
    assert result.status is OrderStatus.CLOSED
    args, _ = client.create_order.await_args
    symbol, otype, side, amount, price, params = args
    assert (symbol, otype, side, amount) == ("BTC/USDT:USDT", "market", "sell", 0.5)
    assert price is None
    assert params["reduceOnly"] is True


@pytest.mark.asyncio
async def test_close_position_without_position_raises() -> None:
    client = AsyncMock()
    client.fetch_positions.return_value = []
    with pytest.raises(InvalidOrder):
        await CcxtAdapter(client).close_position("BTC-USDT")
    client.create_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_fetch_order_maps() -> None:
    client = AsyncMock()
    client.fetch_order.return_value = {
        "id": "ord-9",
        "symbol": "BTC/USDT:USDT",
        "status": "closed",
        "filled": 0.1,
        "average": 100.5,
    }
    result = await CcxtAdapter(client).fetch_order("ord-9", "BTC-USDT")
    assert result.status is OrderStatus.CLOSED
    assert result.average_price == Decimal("100.5")
    client.fetch_order.assert_awaited_once_with("ord-9", "BTC/USDT:USDT")


@pytest.mark.asyncio
async def test_fetch_open_orders_maps_list() -> None:
    client = AsyncMock()
    client.fetch_open_orders.return_value = [
        {"id": "a", "symbol": "BTC/USDT:USDT", "status": "open"},
        {"id": "b", "symbol": "BTC/USDT:USDT", "status": "open"},
    ]
    orders = await CcxtAdapter(client).fetch_open_orders("BTC-USDT")
    assert [o.order_id for o in orders] == ["a", "b"]
    client.fetch_open_orders.assert_awaited_once_with("BTC/USDT:USDT")


@pytest.mark.asyncio
async def test_unknown_order_status_falls_back_to_open() -> None:
    client = AsyncMock()
    client.fetch_order.return_value = {
        "id": "z",
        "symbol": "BTC/USDT:USDT",
        "status": "weird_status",
    }
    result = await CcxtAdapter(client).fetch_order("z", "BTC/USDT:USDT")
    assert result.status is OrderStatus.OPEN
