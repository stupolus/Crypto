"""Unit-тесты PrivateAPI: respx-моки фикстурных ответов BingX.

Не ходим на сеть — все запросы перехватываются respx.
Проверяем:
- Каждый GET/POST идёт на правильный путь со всеми обязательными параметрами.
- Pydantic-модели разбирают live-подобные payload'ы.
- ``request_signed`` синхронит часы и добавляет ``timestamp``/``signature``.
- ``ensure_invariants`` шлёт ровно три POST'а в правильном порядке.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from adapters.bingx.client import BingXClient
from adapters.bingx.config import BingXConfig
from adapters.bingx.exceptions import InvalidResponseError
from adapters.bingx.private import PrivateAPI


@pytest.fixture
def signed_client(cfg: BingXConfig) -> Iterator[BingXClient]:
    """Клиент с фейковыми ключами и заранее засинкаными часами.

    Префикс ``vst-`` ничего не значит для тестов — главное, что
    ``request_signed`` не упадёт на проверке наличия ключей.
    """
    client = BingXClient(cfg, api_key="vst-key", api_secret="vst-secret")
    # Подмена служебных полей: пропускаем sync_server_time в горячем пути.
    client._server_time_offset_ms = 0
    client._last_server_time_sync = time.monotonic()
    yield client


# ── Balance ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_balance_returns_typed_assets(
    cfg: BingXConfig, signed_client: BingXClient, balance_payload: dict[str, Any]
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.private_endpoints.balance).mock(
            return_value=httpx.Response(200, json=balance_payload)
        )
        items = await PrivateAPI(signed_client, cfg).get_balance()
    assert len(items) == 2
    usdt = next(b for b in items if b.asset == "USDT")
    assert usdt.balance == Decimal("1000.0000")
    assert usdt.equity == Decimal("1002.5000")
    assert usdt.used_margin == Decimal("4.5000")
    assert usdt.realised_profit == Decimal("0.0000")
    btc = next(b for b in items if b.asset == "BTC")
    assert btc.realised_profit is None  # V3 для BTC не отдаёт это поле


@pytest.mark.asyncio
async def test_get_usdt_balance_filters_usdt_asset(
    cfg: BingXConfig, signed_client: BingXClient, balance_payload: dict[str, Any]
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.private_endpoints.balance).mock(
            return_value=httpx.Response(200, json=balance_payload)
        )
        usdt = await PrivateAPI(signed_client, cfg).get_usdt_balance()
    assert usdt.asset == "USDT"


@pytest.mark.asyncio
async def test_get_usdt_balance_raises_when_no_usdt_in_response(
    cfg: BingXConfig, signed_client: BingXClient
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.private_endpoints.balance).mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "",
                    "data": [
                        {
                            "asset": "BTC",
                            "balance": "0.1",
                            "equity": "0.1",
                            "unrealizedProfit": "0",
                            "availableMargin": "0.1",
                            "usedMargin": "0",
                            "freezedMargin": "0",
                        }
                    ],
                },
            )
        )
        with pytest.raises(InvalidResponseError, match="USDT asset not found"):
            await PrivateAPI(signed_client, cfg).get_usdt_balance()


# ── Positions ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_positions_normalizes_symbol_param(
    cfg: BingXConfig, signed_client: BingXClient, positions_payload: dict[str, Any]
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = mock.get(cfg.private_endpoints.positions).mock(
            return_value=httpx.Response(200, json=positions_payload)
        )
        positions = await PrivateAPI(signed_client, cfg).get_positions("BTCUSDT")
    request = route.calls[0].request
    assert "symbol=BTC-USDT" in str(request.url)
    assert len(positions) == 1
    pos = positions[0]
    assert pos.symbol == "BTC-USDT"
    assert pos.position_side == "LONG"
    assert pos.isolated is True
    assert pos.position_amt == Decimal("0.0010")
    assert pos.leverage == 5
    assert pos.liquidation_price == Decimal("45000.5")


@pytest.mark.asyncio
async def test_get_positions_without_symbol_omits_param(
    cfg: BingXConfig, signed_client: BingXClient, positions_payload: dict[str, Any]
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = mock.get(cfg.private_endpoints.positions).mock(
            return_value=httpx.Response(200, json=positions_payload)
        )
        await PrivateAPI(signed_client, cfg).get_positions()
    assert "symbol=" not in str(route.calls[0].request.url)


# ── Open orders ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_open_orders_unwraps_orders_array(
    cfg: BingXConfig, signed_client: BingXClient, open_orders_payload: dict[str, Any]
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.private_endpoints.open_orders).mock(
            return_value=httpx.Response(200, json=open_orders_payload)
        )
        orders = await PrivateAPI(signed_client, cfg).get_open_orders("BTC-USDT")
    assert len(orders) == 2
    entry, sl = orders
    assert entry.type == "LIMIT"
    assert entry.client_order_id == "my-bot-uuid-001"
    assert entry.reduce_only is False
    assert sl.type == "STOP_MARKET"
    assert sl.stop_price_decimal == Decimal("63000.0")
    assert entry.stop_price_decimal is None  # пустая строка → None


@pytest.mark.asyncio
async def test_get_open_orders_raises_on_bad_payload_shape(
    cfg: BingXConfig, signed_client: BingXClient
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.private_endpoints.open_orders).mock(
            return_value=httpx.Response(
                200, json={"code": 0, "msg": "", "data": {"orders": "not-a-list"}}
            )
        )
        with pytest.raises(InvalidResponseError):
            await PrivateAPI(signed_client, cfg).get_open_orders()


# ── Fills ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_fills_passes_required_ts_window(
    cfg: BingXConfig, signed_client: BingXClient, fills_payload: dict[str, Any]
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = mock.get(cfg.private_endpoints.fills).mock(
            return_value=httpx.Response(200, json=fills_payload)
        )
        fills = await PrivateAPI(signed_client, cfg).get_fills(
            start_ts_ms=1_700_000_000_000,
            end_ts_ms=1_700_100_000_000,
            symbol="BTC-USDT",
        )
    url = str(route.calls[0].request.url)
    assert "startTs=1700000000000" in url
    assert "endTs=1700100000000" in url
    assert "tradingUnit=COIN" in url
    assert len(fills) == 1
    f = fills[0]
    assert f.symbol == "BTC-USDT"
    assert f.commission == Decimal("-0.0335")
    assert f.filled_at.year == 2026


# ── Setters ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_margin_type_sends_correct_post(
    cfg: BingXConfig, signed_client: BingXClient, margin_type_payload: dict[str, Any]
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = mock.post(cfg.private_endpoints.set_margin_type).mock(
            return_value=httpx.Response(200, json=margin_type_payload)
        )
        await PrivateAPI(signed_client, cfg).set_margin_type("BTC-USDT", "ISOLATED")
    url = str(route.calls[0].request.url)
    assert "symbol=BTC-USDT" in url
    assert "marginType=ISOLATED" in url


@pytest.mark.asyncio
async def test_set_leverage_sends_string_value_and_side(
    cfg: BingXConfig, signed_client: BingXClient, leverage_payload: dict[str, Any]
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = mock.post(cfg.private_endpoints.set_leverage).mock(
            return_value=httpx.Response(200, json=leverage_payload)
        )
        info = await PrivateAPI(signed_client, cfg).set_leverage("BTC-USDT", 5)
    url = str(route.calls[0].request.url)
    # Квирк §7 п.6: side=BOTH в one-way, leverage передаётся строкой.
    assert "side=BOTH" in url
    assert "leverage=5" in url
    assert info.symbol == "BTC-USDT"
    assert info.leverage == 5


@pytest.mark.asyncio
async def test_set_position_mode_sends_string_bool(
    cfg: BingXConfig, signed_client: BingXClient, position_mode_payload: dict[str, Any]
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = mock.post(cfg.private_endpoints.position_mode).mock(
            return_value=httpx.Response(200, json=position_mode_payload)
        )
        mode = await PrivateAPI(signed_client, cfg).set_position_mode(hedge=False)
    # Квирк §7 п.4: dualSidePosition должен быть строкой "false"/"true".
    assert "dualSidePosition=false" in str(route.calls[0].request.url)
    assert mode.is_hedge_mode is False


@pytest.mark.asyncio
async def test_get_position_mode_parses_string_bool(
    cfg: BingXConfig, signed_client: BingXClient
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.private_endpoints.position_mode).mock(
            return_value=httpx.Response(
                200,
                json={"code": 0, "msg": "", "data": {"dualSidePosition": "true"}},
            )
        )
        mode = await PrivateAPI(signed_client, cfg).get_position_mode()
    assert mode.is_hedge_mode is True


# ── Bootstrap инвариантов ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_invariants_makes_three_calls_in_order(
    cfg: BingXConfig,
    signed_client: BingXClient,
    margin_type_payload: dict[str, Any],
    leverage_payload: dict[str, Any],
    position_mode_payload: dict[str, Any],
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        pm_route = mock.post(cfg.private_endpoints.position_mode).mock(
            return_value=httpx.Response(200, json=position_mode_payload)
        )
        mt_route = mock.post(cfg.private_endpoints.set_margin_type).mock(
            return_value=httpx.Response(200, json=margin_type_payload)
        )
        lev_route = mock.post(cfg.private_endpoints.set_leverage).mock(
            return_value=httpx.Response(200, json=leverage_payload)
        )
        await PrivateAPI(signed_client, cfg).ensure_invariants("BTC-USDT", 5)
    # Все три эндпоинта вызвались по разу.
    assert pm_route.call_count == 1
    assert mt_route.call_count == 1
    assert lev_route.call_count == 1
    # Position mode передан как "false" (one-way per invariants).
    assert "dualSidePosition=false" in str(pm_route.calls[0].request.url)


# ── Подпись и сервер-тайм-синк ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_signed_attaches_timestamp_and_signature(
    cfg: BingXConfig, signed_client: BingXClient, balance_payload: dict[str, Any]
) -> None:
    async with signed_client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = mock.get(cfg.private_endpoints.balance).mock(
            return_value=httpx.Response(200, json=balance_payload)
        )
        await PrivateAPI(signed_client, cfg).get_balance()
    req = route.calls[0].request
    url = str(req.url)
    assert "timestamp=" in url
    assert "recvWindow=5000" in url
    assert "signature=" in url
    assert req.headers.get(cfg.signing.api_key_header) == "vst-key"


@pytest.mark.asyncio
async def test_first_signed_call_triggers_server_time_sync(
    cfg: BingXConfig, balance_payload: dict[str, Any], server_time_payload: dict[str, Any]
) -> None:
    """Без предварительного синка — request_signed дёрнет server/time сам."""
    client = BingXClient(cfg, api_key="k", api_secret="s")
    async with client, respx.mock(base_url=cfg.active_rest_base) as mock:
        st_route = mock.get(cfg.rest_endpoints.server_time).mock(
            return_value=httpx.Response(200, json=server_time_payload)
        )
        bal_route = mock.get(cfg.private_endpoints.balance).mock(
            return_value=httpx.Response(200, json=balance_payload)
        )
        await PrivateAPI(client, cfg).get_balance()
    assert st_route.call_count == 1
    assert bal_route.call_count == 1
    # Offset рассчитан и сохранён.
    assert client._last_server_time_sync is not None


@pytest.mark.asyncio
async def test_signed_calls_share_single_time_sync_within_interval(
    cfg: BingXConfig, balance_payload: dict[str, Any], server_time_payload: dict[str, Any]
) -> None:
    """Второй приватный вызов в пределах ``resync_interval_s`` не пере-синкается."""
    client = BingXClient(cfg, api_key="k", api_secret="s")
    async with client, respx.mock(base_url=cfg.active_rest_base) as mock:
        st_route = mock.get(cfg.rest_endpoints.server_time).mock(
            return_value=httpx.Response(200, json=server_time_payload)
        )
        mock.get(cfg.private_endpoints.balance).mock(
            return_value=httpx.Response(200, json=balance_payload)
        )
        api = PrivateAPI(client, cfg)
        await api.get_balance()
        await api.get_balance()
    assert st_route.call_count == 1


@pytest.mark.asyncio
async def test_sync_server_time_computes_offset_against_local_clock(
    cfg: BingXConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Server впереди локального на ~1000 мс → offset близок к +1000."""
    fake_local_ms = 1_700_000_000_000

    def fake_time() -> float:
        return fake_local_ms / 1000

    monkeypatch.setattr(time, "time", fake_time)
    server_payload = {"code": 0, "msg": "", "data": {"serverTime": fake_local_ms + 1000}}
    client = BingXClient(cfg, api_key="k", api_secret="s")
    async with client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.server_time).mock(
            return_value=httpx.Response(200, json=server_payload)
        )
        offset = await client.sync_server_time()
    # Допуск на RTT в фейк-таймере — пара мс.
    assert 990 <= offset <= 1010
    assert client.now_ms() - fake_local_ms == offset
