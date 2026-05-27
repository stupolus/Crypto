"""Integration-тесты ордеров на VST (фаза 0.D part 1).

Запуск: ``pytest -m integration adapters/bingx/tests/test_int_orders.py``.
Требует ``BINGX_VST_API_KEY`` / ``BINGX_VST_API_SECRET`` в ``.env`` и
ненулевой VST-баланс.

Гарантия чистоты: каждый тест в ``finally`` зовёт ``close_position`` —
позиция не остаётся открытой даже при падении.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio

from adapters.bingx.client import BingXClient
from adapters.bingx.private import PrivateAPI
from adapters.bingx.private_models import OrderRequest
from adapters.bingx.public import PublicAPI
from adapters.bingx.settings import BingXSettings


@pytest.fixture
def settings() -> BingXSettings:
    try:
        s = BingXSettings()
    except Exception as e:  # pragma: no cover - на CI без .env пропускаем
        pytest.skip(f"BingXSettings unavailable: {e}")
    if not s.active_key or not s.active_secret:
        pytest.skip("BINGX_VST_API_KEY/SECRET not set in .env")
    if s.env != "vst":
        pytest.skip("integration-тесты ордеров запускаем только на VST")
    return s


@pytest_asyncio.fixture
async def api(settings: BingXSettings) -> AsyncIterator[PrivateAPI]:
    async with BingXClient(settings=settings) as c:
        yield PrivateAPI(c)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_int_open_market_with_sl_then_close_btc_usdt(
    api: PrivateAPI,
    settings: BingXSettings,
) -> None:
    """Полный жизненный цикл позиции на BTC-USDT:

    1. Берём текущую цену через PublicAPI.
    2. Размещаем market BUY 0.0001 BTC с attached SL на -1% от текущей цены.
    3. Подтверждаем что позиция открылась (`positionAmt > 0`).
    4. `close_position` → reduce_only market SELL.
    5. Подтверждаем что позиция закрыта (`positionAmt == 0`).
    """
    symbol = "BTC-USDT"
    # Берём mark price для расчёта SL.
    async with BingXClient(settings=settings) as pub_client:
        ticker = await PublicAPI(pub_client, pub_client.config).get_ticker(symbol)
        last_price = ticker.last_price

    # Минимальный размер для BTC-USDT — tradeMinUSDT=2, при цене ~60-100k
    # хватит 0.0001 BTC. SL ставим на 1% ниже, округляя до точности
    # символа (BingX молча усекает — см. plans/01 §4.1 п.2).
    sl_price = (last_price * Decimal("0.99")).quantize(Decimal("0.1"))
    qty = Decimal("0.0001")

    req = OrderRequest(
        symbol=symbol,
        side="BUY",
        position_side="LONG",
        order_type="MARKET",
        quantity=qty,
        attached_stop_loss=sl_price,
    )

    try:
        order = await api.place_order(req)
        assert order.symbol == symbol
        # MARKET-ордер обычно сразу FILLED или PENDING.
        assert order.status in {"NEW", "PENDING", "FILLED", "PARTIALLY_FILLED"}

        # Проверяем позицию.
        positions = await api.get_positions(symbol)
        opened = next((p for p in positions if p.position_amount != 0), None)
        assert opened is not None, "позиция должна была открыться"
        assert opened.position_amount > 0, "ожидаем LONG (BUY)"

        # Закрываем kill-switch'ем.
        close = await api.close_position(symbol)
        assert close is not None, "ожидаем market-ордер закрытия"
        assert close.side == "SELL"

        # Проверяем что позиция теперь нулевая.
        positions_after = await api.get_positions(symbol)
        for p in positions_after:
            assert p.position_amount == 0, f"позиция не закрылась: {p}"
    finally:
        # Подстраховка: если выше что-то упало — закрыть.
        with contextlib.suppress(Exception):
            await api.close_position(symbol)
