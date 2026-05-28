"""Тесты account-слоя адаптера (ccxt замокан, без сети)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from exchanges.ccxt_base import CcxtAdapter
from exchanges.errors import MarginModeError
from exchanges.models import MarginMode, PositionSide


@pytest.mark.asyncio
async def test_fetch_balance_maps_usdt() -> None:
    client = AsyncMock()
    client.fetch_balance.return_value = {
        "USDT": {"free": 900.0, "used": 100.0, "total": 1000.0},
    }
    bal = await CcxtAdapter(client).fetch_balance()
    assert bal.asset == "USDT"
    assert bal.free == Decimal("900.0")
    assert bal.total == Decimal("1000.0")


@pytest.mark.asyncio
async def test_fetch_balance_missing_usdt_is_zero() -> None:
    client = AsyncMock()
    client.fetch_balance.return_value = {}
    bal = await CcxtAdapter(client).fetch_balance()
    assert bal.total == Decimal("0")


@pytest.mark.asyncio
async def test_fetch_positions_maps_and_filters_zero() -> None:
    client = AsyncMock()
    client.fetch_positions.return_value = [
        {
            "symbol": "BTC/USDT:USDT",
            "side": "long",
            "contracts": 0.5,
            "entryPrice": 100.0,
            "markPrice": 101.0,
            "leverage": 3.0,
            "marginMode": "isolated",
            "unrealizedPnl": 0.5,
            "liquidationPrice": 80.0,
        },
        {"symbol": "ETH/USDT:USDT", "side": "short", "contracts": 0.0},
    ]
    positions = await CcxtAdapter(client).fetch_positions(["BTC-USDT", "ETH-USDT"])
    assert len(positions) == 1
    pos = positions[0]
    assert pos.symbol == "BTC/USDT:USDT"
    assert pos.side is PositionSide.LONG
    assert pos.size == Decimal("0.5")
    assert pos.liquidation_price == Decimal("80.0")
    # символы нормализованы перед вызовом ccxt
    client.fetch_positions.assert_awaited_once_with(["BTC/USDT:USDT", "ETH/USDT:USDT"])


@pytest.mark.asyncio
async def test_fetch_positions_no_symbols_passes_none() -> None:
    client = AsyncMock()
    client.fetch_positions.return_value = []
    await CcxtAdapter(client).fetch_positions()
    client.fetch_positions.assert_awaited_once_with(None)


@pytest.mark.asyncio
async def test_set_leverage_delegates_normalized() -> None:
    client = AsyncMock()
    await CcxtAdapter(client).set_leverage("BTC-USDT", 3)
    client.set_leverage.assert_awaited_once_with(3, "BTC/USDT:USDT")


@pytest.mark.asyncio
async def test_set_margin_mode_isolated_delegates() -> None:
    client = AsyncMock()
    await CcxtAdapter(client).set_margin_mode("BTC-USDT", MarginMode.ISOLATED)
    client.set_margin_mode.assert_awaited_once_with("isolated", "BTC/USDT:USDT")


@pytest.mark.asyncio
async def test_set_margin_mode_cross_rejected_without_network() -> None:
    client = AsyncMock()
    with pytest.raises(MarginModeError):
        await CcxtAdapter(client).set_margin_mode("BTC-USDT", MarginMode.CROSS)
    client.set_margin_mode.assert_not_awaited()
