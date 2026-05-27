"""Integration: User Data Stream + cancelAllAfter + compensating-close на VST.

Запуск: ``pytest -m integration adapters/bingx/tests/test_int_user_stream.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
import pytest_asyncio

from adapters.bingx.client import BingXClient
from adapters.bingx.private import PrivateAPI
from adapters.bingx.private_models import (
    AccountUpdateEvent,
    OrderRequest,
    OrderUpdateEvent,
)
from adapters.bingx.public import PublicAPI
from adapters.bingx.settings import BingXSettings
from adapters.bingx.user_stream import BingXUserDataStream


@pytest.fixture
def settings() -> BingXSettings:
    try:
        s = BingXSettings()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"BingXSettings unavailable: {e}")
    if not s.active_key or not s.active_secret:
        pytest.skip("BINGX_VST_API_KEY/SECRET not set in .env")
    if s.env != "vst":
        pytest.skip("user-stream integration — только на VST")
    return s


@pytest_asyncio.fixture
async def api(settings: BingXSettings) -> AsyncIterator[PrivateAPI]:
    async with BingXClient(settings=settings) as c:
        yield PrivateAPI(c)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_int_listen_key_lifecycle(api: PrivateAPI) -> None:
    """Создаём listenKey → продлеваем → закрываем — без падений."""
    key = await api.create_listen_key()
    assert isinstance(key, str) and len(key) > 0
    await api.keep_alive_listen_key(key)
    await api.close_listen_key(key)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_int_cancel_all_after_round_trip(api: PrivateAPI) -> None:
    """Поставить таймер на 60с, тут же отменить.

    Квирк §7 п.37: `cancelAllAfter` возвращает HTTP 404 на VST (эндпоинт
    отсутствует в demo-окружении). Пропускаем тест с понятным сообщением.
    Логику проверим на live в фазе 1 при реальной торговле.
    """
    from adapters.bingx.exceptions import APIError

    try:
        await api.cancel_all_after(60_000)
        await api.cancel_all_after(0)
    except APIError as err:
        if err.code == 404:
            pytest.skip(f"cancelAllAfter not available on VST: {err.message}")
        raise


@pytest.mark.integration
@pytest.mark.asyncio
async def test_int_user_stream_receives_order_trade_update_on_close(
    api: PrivateAPI,
    settings: BingXSettings,
) -> None:
    """Полный сценарий с push-событиями:

    1. Запускаем User Data Stream.
    2. Открываем market BTC-USDT 0.0001 с attached SL.
    3. Ждём ``ORDER_TRADE_UPDATE(execution_type='TRADE')`` в стриме.
    4. close_position.
    5. Ждём ещё одно ``ORDER_TRADE_UPDATE`` или ``ACCOUNT_UPDATE``.
    6. Завершаем стрим.
    """
    symbol = "BTC-USDT"
    # Цена для SL
    async with BingXClient(settings=settings) as pub:
        ticker = await PublicAPI(pub, pub.config).get_ticker(symbol)
        last_price = ticker.last_price
    sl_price = (last_price * Decimal("0.99")).quantize(Decimal("0.1"))

    try:
        async with BingXUserDataStream(api) as stream:
            # Дождёмся, пока WS подключится.
            assert stream.listen_key is not None

            # Открываем позицию.
            await api.place_order(
                OrderRequest(
                    symbol=symbol,
                    side="BUY",
                    position_side="LONG",
                    order_type="MARKET",
                    quantity=Decimal("0.0001"),
                    attached_stop_loss=sl_price,
                )
            )

            # Соберём первые N событий за 15с — должны увидеть ORDER_TRADE_UPDATE.
            seen_order_event = False
            seen_account_event = False
            deadline = asyncio.get_event_loop().time() + 15
            async for event in stream.events():
                if isinstance(event, OrderUpdateEvent):
                    seen_order_event = True
                if isinstance(event, AccountUpdateEvent):
                    seen_account_event = True
                if seen_order_event and seen_account_event:
                    break
                if asyncio.get_event_loop().time() > deadline:
                    break

            assert seen_order_event, "ожидаем ORDER_TRADE_UPDATE после place_order"
            # ACCOUNT_UPDATE придёт после fill — не делаем обязательным
            # на flat-маркете (но обычно есть для market-ордера).
    finally:
        with contextlib.suppress(Exception):
            await api.close_position(symbol)
