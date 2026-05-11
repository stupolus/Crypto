"""Unit-тесты ``adapters.bingx.private.PrivateAPI``.

Все тесты — изоляция от живого API через respx. ServerTime моки даём общим
helper'ом, чтобы time_syncer проходил lazy-init без сетевых запросов.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from adapters.bingx.client import BingXClient
from adapters.bingx.config import BingXConfig
from adapters.bingx.exceptions import APIError
from adapters.bingx.private import PrivateAPI

_TEST_KEY = "test-api-key"
_TEST_SECRET = "test-api-secret"


def _stub_server_time(mock: respx.MockRouter, cfg: BingXConfig) -> None:
    mock.get(cfg.rest_endpoints.server_time).mock(
        return_value=httpx.Response(
            200, json={"code": 0, "msg": "", "data": {"serverTime": 1_700_000_000_000}}
        )
    )


def _ok(data: Any) -> dict[str, Any]:
    return {"code": 0, "msg": "", "data": data}


def _err(code: int, msg: str) -> dict[str, Any]:
    return {"code": code, "msg": msg, "data": None}


# ── get_balance ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_balance_parses_decimal_fields(cfg: BingXConfig) -> None:
    payload = _ok(
        [
            {
                "userId": "123",
                "asset": "USDT",
                "balance": "10000.12345678",
                "equity": "10001.0",
                "unrealizedProfit": "0.5",
                "realisedProfit": "12.34",
                "availableMargin": "9000.0",
                "usedMargin": "1000.12345678",
                "freezedMargin": "0",
            }
        ]
    )
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        mock.get(cfg.rest_endpoints.balance).mock(
            return_value=httpx.Response(200, json=payload)
        )
        balances = await PrivateAPI(client).get_balance()
    assert len(balances) == 1
    b = balances[0]
    assert b.asset == "USDT"
    assert b.balance == Decimal("10000.12345678")
    assert b.available_margin == Decimal("9000.0")
    assert b.unrealized_profit == Decimal("0.5")


@pytest.mark.asyncio
async def test_get_balance_handles_object_payload(cfg: BingXConfig) -> None:
    """BingX V3 иногда возвращает один объект (не массив)."""
    payload = _ok(
        {
            "userId": "u",
            "asset": "USDT",
            "balance": "1",
            "equity": "1",
            "unrealizedProfit": "0",
            "availableMargin": "1",
            "usedMargin": "0",
        }
    )
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        mock.get(cfg.rest_endpoints.balance).mock(
            return_value=httpx.Response(200, json=payload)
        )
        balances = await PrivateAPI(client).get_balance()
    assert len(balances) == 1
    assert balances[0].asset == "USDT"


# ── get_positions ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_positions_parses_position_fields(cfg: BingXConfig) -> None:
    payload = _ok(
        [
            {
                "symbol": "BTC-USDT",
                "positionId": "p1",
                "positionSide": "BOTH",
                "positionAmt": "0.001",
                "availableAmt": "0.001",
                "avgPrice": "50000.0",
                "markPrice": "50100.0",
                "leverage": 3,
                "marginType": "ISOLATED",
                "isolatedMargin": "16.7",
                "unrealizedProfit": "0.1",
                "liquidationPrice": "40000.0",
                "updateTime": 1700000000000,
            }
        ]
    )
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        mock.get(cfg.rest_endpoints.positions).mock(
            return_value=httpx.Response(200, json=payload)
        )
        positions = await PrivateAPI(client).get_positions("BTC-USDT")
    assert len(positions) == 1
    p = positions[0]
    assert p.symbol == "BTC-USDT"
    assert p.position_side == "BOTH"
    assert p.leverage == 3
    assert p.margin_type == "ISOLATED"
    assert p.position_amount == Decimal("0.001")


@pytest.mark.asyncio
async def test_get_positions_validates_symbol_hyphen(cfg: BingXConfig) -> None:
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client:
        with pytest.raises(ValueError):
            await PrivateAPI(client).get_positions("BTCUSDT")


# ── get_open_orders ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_open_orders_unwraps_orders_field(cfg: BingXConfig) -> None:
    payload = _ok(
        {
            "orders": [
                {
                    "orderId": "111",
                    "clientOrderID": "co-1",
                    "symbol": "BTC-USDT",
                    "side": "BUY",
                    "positionSide": "BOTH",
                    "type": "LIMIT",
                    "status": "NEW",
                    "price": "30000.0",
                    "origQty": "0.001",
                    "executedQty": "0",
                    "avgPrice": "0",
                    "stopPrice": None,
                    "time": 1700000000000,
                    "updateTime": 1700000000500,
                    "reduceOnly": False,
                }
            ]
        }
    )
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        mock.get(cfg.rest_endpoints.open_orders).mock(
            return_value=httpx.Response(200, json=payload)
        )
        orders = await PrivateAPI(client).get_open_orders("BTC-USDT")
    assert len(orders) == 1
    assert orders[0].order_id == "111"
    assert orders[0].status == "NEW"


# ── get_fills ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_fills_unwraps_fill_history_orders(cfg: BingXConfig) -> None:
    payload = _ok(
        {
            "fill_history_orders": [
                {
                    "tradeId": "t1",
                    "orderId": "o1",
                    "symbol": "BTC-USDT",
                    "side": "BUY",
                    "positionSide": "BOTH",
                    "price": "50000",
                    "qty": "0.001",
                    "quoteQty": "50.0",
                    "commission": "-0.025",
                    "commissionAsset": "USDT",
                    "realisedPNL": "0",
                    "maker": False,
                    "time": 1700000000000,
                }
            ]
        }
    )
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        mock.get(cfg.rest_endpoints.fills).mock(
            return_value=httpx.Response(200, json=payload)
        )
        fills = await PrivateAPI(client).get_fills("BTC-USDT", limit=10)
    assert len(fills) == 1
    assert fills[0].trade_id == "t1"
    assert fills[0].commission == Decimal("-0.025")
    assert fills[0].is_maker is False


@pytest.mark.asyncio
async def test_get_fills_rejects_invalid_limit(cfg: BingXConfig) -> None:
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client:
        api = PrivateAPI(client)
        with pytest.raises(ValueError):
            await api.get_fills("BTC-USDT", limit=0)
        with pytest.raises(ValueError):
            await api.get_fills("BTC-USDT", limit=1001)


# ── set_margin_mode (idempotent) ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_margin_mode_sends_isolated_param(cfg: BingXConfig) -> None:
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        route = mock.post(cfg.rest_endpoints.set_margin_type).mock(
            return_value=httpx.Response(200, json=_ok({}))
        )
        await PrivateAPI(client).set_margin_mode("BTC-USDT", "ISOLATED")
    call = route.calls.last
    params = dict(call.request.url.params)
    assert params["symbol"] == "BTC-USDT"
    assert params["marginType"] == "ISOLATED"


@pytest.mark.asyncio
async def test_set_margin_mode_idempotent_on_80012(cfg: BingXConfig) -> None:
    """code=80012 («No need to switch») — успех."""
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        mock.post(cfg.rest_endpoints.set_margin_type).mock(
            return_value=httpx.Response(200, json=_err(80012, "No need to switch"))
        )
        await PrivateAPI(client).set_margin_mode("BTC-USDT")  # не должно бросить


@pytest.mark.asyncio
async def test_set_margin_mode_propagates_other_errors(cfg: BingXConfig) -> None:
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        mock.post(cfg.rest_endpoints.set_margin_type).mock(
            return_value=httpx.Response(200, json=_err(80099, "permission denied"))
        )
        with pytest.raises(APIError):
            await PrivateAPI(client).set_margin_mode("BTC-USDT")


# ── set_leverage ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_leverage_validates_range(cfg: BingXConfig) -> None:
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client:
        api = PrivateAPI(client)
        with pytest.raises(ValueError):
            await api.set_leverage("BTC-USDT", 0)
        with pytest.raises(ValueError):
            await api.set_leverage("BTC-USDT", 200)


@pytest.mark.asyncio
async def test_set_leverage_sends_params(cfg: BingXConfig) -> None:
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        route = mock.post(cfg.rest_endpoints.set_leverage).mock(
            return_value=httpx.Response(200, json=_ok({}))
        )
        await PrivateAPI(client).set_leverage("BTC-USDT", 3)
    params = dict(route.calls.last.request.url.params)
    assert params["leverage"] == "3"
    assert params["side"] == "BOTH"


# ── set_position_mode ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_position_mode_one_way_sends_false_string(cfg: BingXConfig) -> None:
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        route = mock.post(cfg.rest_endpoints.set_position_mode).mock(
            return_value=httpx.Response(200, json=_ok({}))
        )
        await PrivateAPI(client).set_position_mode(one_way=True)
    params = dict(route.calls.last.request.url.params)
    assert params["dualSidePosition"] == "false"


@pytest.mark.asyncio
async def test_set_position_mode_idempotent_on_no_need_message(cfg: BingXConfig) -> None:
    """Сообщение «no need to switch» = успех, даже на неизвестном коде."""
    async with BingXClient(
        cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET
    ) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        _stub_server_time(mock, cfg)
        mock.post(cfg.rest_endpoints.set_position_mode).mock(
            return_value=httpx.Response(
                200, json=_err(99999, "no need to switch position side")
            )
        )
        await PrivateAPI(client).set_position_mode(one_way=True)
