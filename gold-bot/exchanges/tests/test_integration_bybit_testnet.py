"""Integration-тесты: реальная сеть. По умолчанию НЕ запускаются.

Запуск вручную: `pytest -m integration` (из каталога gold-bot).

- Публичные эндпоинты (fetch_markets) не требуют ключей — проверяют
  связность и наличие нужных инструментов.
- Полный торговый цикл на Bybit testnet требует ключей в env:
  BYBIT_TESTNET_API_KEY / BYBIT_TESTNET_API_SECRET. Без них — skip.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from exchanges.bingx import BingXAdapter
from exchanges.bybit import BybitAdapter
from exchanges.models import MarginMode, OrderRequest, OrderSide, OrderType

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_bybit_public_markets_reachable() -> None:
    adapter = BybitAdapter()
    try:
        markets = await adapter.fetch_markets()
    finally:
        await adapter.close()
    assert any("BTC/USDT" in m for m in markets)


@pytest.mark.asyncio
async def test_bingx_public_markets_reachable() -> None:
    adapter = BingXAdapter()
    try:
        markets = await adapter.fetch_markets()
    finally:
        await adapter.close()
    assert any("BTC/USDT" in m for m in markets)


@pytest.mark.asyncio
async def test_bybit_testnet_order_cycle() -> None:
    api_key = os.environ.get("BYBIT_TESTNET_API_KEY", "")
    api_secret = os.environ.get("BYBIT_TESTNET_API_SECRET", "")
    if not api_key or not api_secret:
        pytest.skip("нет BYBIT_TESTNET ключей в env")

    symbol = "BTC/USDT:USDT"
    adapter = BybitAdapter(api_key, api_secret, testnet=True)
    try:
        await adapter.set_margin_mode(symbol, MarginMode.ISOLATED)
        ticker = await adapter.fetch_ticker(symbol)
        stop = (ticker.last * Decimal("0.97")).quantize(Decimal("0.1"))
        request = OrderRequest(
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.001"),
            stop_price=stop,
        )
        order = await adapter.place_order(request)
        assert order.order_id
        positions = await adapter.fetch_positions([symbol])
        assert any(p.symbol == symbol for p in positions)
        closed = await adapter.close_position(symbol)
        assert closed.order_id
    finally:
        await adapter.close()
