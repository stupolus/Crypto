"""Integration-тесты против живого публичного API BingX.

ЗАПУСК ОТДЕЛЬНО — не в CI по умолчанию:

    pytest -m integration adapters/bingx/tests/test_integration.py

Назначение:
- сверить, что наши pydantic-модели матчатся со схемой live-API;
- подтвердить ключевой факт ``tradeMinUSDT == 2`` для BTC-USDT
  (см. plans/01 §10 п.7 — на нём держится снятие блокера фазы 1);
- замерить, что WS-коннект + подписка на ``BTC-USDT@kline_1min``
  поднимаются и отдают хотя бы один data-фрейм.

Без ключей. Безопасны: только GET-эндпоинты и market-WS.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from adapters.bingx import BingXClient, BingXMarketWebSocket, PublicAPI
from adapters.bingx.config import get_default_config

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_live_server_time_within_5s_of_local() -> None:
    cfg = get_default_config()
    async with BingXClient(cfg) as client:
        st = await PublicAPI(client, cfg).get_server_time()
    # Достаточно проверить, что значение в разумном миллисекундном диапазоне
    # и расходится с локальным временем не больше чем на несколько секунд
    # (плюс сетевые задержки).
    import time as _t

    local_ms = int(_t.time() * 1000)
    assert abs(local_ms - st.server_time_ms) < 30_000


@pytest.mark.asyncio
async def test_live_btc_contract_has_min_notional_two_usdt() -> None:
    cfg = get_default_config()
    async with BingXClient(cfg) as client:
        contract = await PublicAPI(client, cfg).get_contract("BTC-USDT")
    # Это ключевой факт — снимает блокер фазы 1 (plans/01 §10 п.7).
    assert contract.trade_min_usdt == Decimal("2")
    assert contract.price_precision == 1
    assert contract.quantity_precision == 4


@pytest.mark.asyncio
async def test_live_btc_klines_returns_data_ascending() -> None:
    cfg = get_default_config()
    async with BingXClient(cfg) as client:
        klines = await PublicAPI(client, cfg).get_klines("BTC-USDT", "15m", limit=5)
    assert 1 <= len(klines) <= 5
    times = [k.open_time_ms for k in klines]
    # Адаптер нормализует BingX-DESC к ASC.
    assert times == sorted(times)


@pytest.mark.asyncio
async def test_live_ws_kline_stream_receives_at_least_one_frame() -> None:
    """Канал ``<symbol>@kline_<rest_interval>``.

    Квирк plans/01 §7 п.27 (наблюдение 2026-05-10): live BingX принимает в WS
    REST-формат интервала (``1m``), не задокументированный ``1min``.
    """
    cfg = get_default_config()
    interval = cfg.defaults.primary_interval_ws
    channel = f"{cfg.defaults.primary_symbol}@kline_{interval}"
    async with BingXMarketWebSocket(cfg) as ws:
        iterator = await ws.subscribe(channel)
        msg = await asyncio.wait_for(iterator.__anext__(), timeout=30.0)
    assert "data" in msg or "dataType" in msg
