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
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        mock.get(cfg.rest_endpoints.balance).mock(return_value=httpx.Response(200, json=payload))
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
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        mock.get(cfg.rest_endpoints.balance).mock(return_value=httpx.Response(200, json=payload))
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
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        mock.get(cfg.rest_endpoints.positions).mock(return_value=httpx.Response(200, json=payload))
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
    async with BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client:
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
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
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
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        mock.get(cfg.rest_endpoints.fills).mock(return_value=httpx.Response(200, json=payload))
        fills = await PrivateAPI(client).get_fills("BTC-USDT", limit=10)
    assert len(fills) == 1
    assert fills[0].trade_id == "t1"
    assert fills[0].commission == Decimal("-0.025")
    assert fills[0].is_maker is False


@pytest.mark.asyncio
async def test_get_fills_rejects_invalid_limit(cfg: BingXConfig) -> None:
    async with BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client:
        api = PrivateAPI(client)
        with pytest.raises(ValueError):
            await api.get_fills("BTC-USDT", limit=0)
        with pytest.raises(ValueError):
            await api.get_fills("BTC-USDT", limit=1001)


# ── set_margin_mode (idempotent) ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_margin_mode_sends_isolated_param(cfg: BingXConfig) -> None:
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
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
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        mock.post(cfg.rest_endpoints.set_margin_type).mock(
            return_value=httpx.Response(200, json=_err(80012, "No need to switch"))
        )
        await PrivateAPI(client).set_margin_mode("BTC-USDT")  # не должно бросить


@pytest.mark.asyncio
async def test_set_margin_mode_propagates_other_errors(cfg: BingXConfig) -> None:
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        mock.post(cfg.rest_endpoints.set_margin_type).mock(
            return_value=httpx.Response(200, json=_err(80099, "permission denied"))
        )
        with pytest.raises(APIError):
            await PrivateAPI(client).set_margin_mode("BTC-USDT")


# ── set_leverage ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_leverage_validates_range(cfg: BingXConfig) -> None:
    async with BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client:
        api = PrivateAPI(client)
        with pytest.raises(ValueError):
            await api.set_leverage("BTC-USDT", 0)
        with pytest.raises(ValueError):
            await api.set_leverage("BTC-USDT", 200)


@pytest.mark.asyncio
async def test_set_leverage_sends_params(cfg: BingXConfig) -> None:
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
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
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
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
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        mock.post(cfg.rest_endpoints.set_position_mode).mock(
            return_value=httpx.Response(200, json=_err(99999, "no need to switch position side"))
        )
        await PrivateAPI(client).set_position_mode(one_way=True)


# ─── place_order / cancel / close (фаза 0.D part 1) ────────────────────────


import json as _json  # noqa: E402

from adapters.bingx.private_models import OrderRequest  # noqa: E402


def _stop_market_order_stub() -> dict[str, Any]:
    """Заглушка attached SL в openOrders: STOP_MARKET + reduce_only=True."""
    return {
        "orderId": "9999",
        "symbol": "BTC-USDT",
        "side": "SELL",
        "positionSide": "BOTH",
        "type": "STOP_MARKET",
        "status": "NEW",
        "price": "0",
        "origQty": "0.001",
        "executedQty": "0",
        "stopPrice": "60000",
        "time": 1_700_000_000_000,
        "updateTime": 1_700_000_000_500,
        "reduceOnly": True,
    }


def _order_ok_payload(
    order_id: str = "1001",
    status: str = "NEW",
    with_stop_loss: bool = True,
) -> dict[str, Any]:
    return {
        "order": {
            "orderId": order_id,
            "clientOrderID": "abcd1234",
            "symbol": "BTC-USDT",
            "side": "BUY",
            "positionSide": "BOTH",
            "type": "MARKET",
            "status": status,
            "price": "0",
            "origQty": "0.001",
            "executedQty": "0",
            "avgPrice": "0",
            "stopPrice": "0",
            "stopLoss": (
                '{"type":"STOP_MARKET","stopPrice":60000,"workingType":"MARK_PRICE"}'
                if with_stop_loss
                else ""
            ),
            "takeProfit": "",
            "time": 1_700_000_001_000,
            "updateTime": 1_700_000_001_500,
            "reduceOnly": False,
        }
    }


@pytest.mark.asyncio
async def test_place_order_market_with_attached_sl_serializes_stop_loss_as_json(
    cfg: BingXConfig,
) -> None:
    """Атомарный entry+SL: ``stopLoss`` — stringified JSON (квирк §7 п.7)."""
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        route = mock.post(cfg.rest_endpoints.place_order).mock(
            return_value=httpx.Response(200, json=_ok(_order_ok_payload()))
        )
        req = OrderRequest(
            symbol="BTC-USDT",
            side="BUY",
            position_side="LONG",
            order_type="MARKET",
            quantity=Decimal("0.001"),
            attached_stop_loss=Decimal("60000"),
            client_order_id="my-uuid-001",
        )
        result = await PrivateAPI(client).place_order(req)

    assert result.order_id == "1001"
    sent = dict(route.calls.last.request.url.params)
    assert sent["symbol"] == "BTC-USDT"
    assert sent["side"] == "BUY"
    assert sent["type"] == "MARKET"
    assert sent["quantity"] == "0.001"
    assert sent["clientOrderID"] == "my-uuid-001"
    # stopLoss — JSON-строка с STOP_MARKET + MARK_PRICE.
    parsed = _json.loads(sent["stopLoss"])
    assert parsed["type"] == "STOP_MARKET"
    # Квирк §7 п.32: stopPrice — JSON-число, не строка.
    assert parsed["stopPrice"] == 60000
    assert isinstance(parsed["stopPrice"], int | float)
    assert parsed["workingType"] == "MARK_PRICE"


@pytest.mark.asyncio
async def test_place_order_limit_with_take_profit_includes_price_and_tif(
    cfg: BingXConfig,
) -> None:
    """LIMIT order: price + timeInForce + takeProfit JSON-сериализован."""
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        payload = _order_ok_payload(order_id="2002")
        payload["order"]["type"] = "LIMIT"
        payload["order"]["price"] = "65000"
        route = mock.post(cfg.rest_endpoints.place_order).mock(
            return_value=httpx.Response(200, json=_ok(payload))
        )
        req = OrderRequest(
            symbol="BTC-USDT",
            side="BUY",
            position_side="LONG",
            order_type="LIMIT",
            quantity=Decimal("0.001"),
            price=Decimal("65000"),
            attached_stop_loss=Decimal("60000"),
            attached_take_profit=Decimal("70000"),
            time_in_force="IOC",
        )
        await PrivateAPI(client).place_order(req)

    sent = dict(route.calls.last.request.url.params)
    assert sent["type"] == "LIMIT"
    assert sent["price"] == "65000"
    assert sent["timeInForce"] == "IOC"
    tp = _json.loads(sent["takeProfit"])
    assert tp["type"] == "TAKE_PROFIT_MARKET"
    assert tp["stopPrice"] == 70000
    assert isinstance(tp["stopPrice"], int | float)


def test_order_request_rejects_entry_without_stop_loss() -> None:
    """Инвариант проекта: нет позиции без SL на бирже."""
    with pytest.raises(ValueError, match="attached_stop_loss"):
        OrderRequest(
            symbol="BTC-USDT",
            side="BUY",
            position_side="LONG",
            order_type="MARKET",
            quantity=Decimal("0.001"),
        )


def test_order_request_rejects_reduce_only_with_stop_loss() -> None:
    with pytest.raises(ValueError, match="close order must not carry"):
        OrderRequest(
            symbol="BTC-USDT",
            side="SELL",
            position_side="LONG",
            order_type="MARKET",
            quantity=Decimal("0.001"),
            reduce_only=True,
            attached_stop_loss=Decimal("60000"),
        )


def test_order_request_closes_position_skips_entry_stop_invariant() -> None:
    """closes_position=True (hedge close) не требует attached_stop_loss и
    не шлёт reduceOnly — валиден без стопа."""
    req = OrderRequest(
        symbol="NCSINASDAQ1002USD-USDT",
        side="SELL",
        position_side="LONG",
        order_type="MARKET",
        quantity=Decimal("0.09"),
        reduce_only=False,
        closes_position=True,
    )
    assert req.closes_position is True
    assert req.reduce_only is False
    assert req.attached_stop_loss is None


def test_order_request_rejects_limit_without_price() -> None:
    with pytest.raises(ValueError, match="LIMIT order requires price"):
        OrderRequest(
            symbol="BTC-USDT",
            side="BUY",
            position_side="LONG",
            order_type="LIMIT",
            quantity=Decimal("0.001"),
            attached_stop_loss=Decimal("60000"),
        )


def test_order_request_rejects_market_with_price() -> None:
    with pytest.raises(ValueError, match="MARKET order must not have price"):
        OrderRequest(
            symbol="BTC-USDT",
            side="BUY",
            position_side="LONG",
            order_type="MARKET",
            quantity=Decimal("0.001"),
            price=Decimal("65000"),
            attached_stop_loss=Decimal("60000"),
        )


@pytest.mark.asyncio
async def test_cancel_order_requires_id_or_client_id(cfg: BingXConfig) -> None:
    async with BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client:
        api = PrivateAPI(client)
        with pytest.raises(ValueError, match="order_id or client_order_id"):
            await api.cancel_order("BTC-USDT")


@pytest.mark.asyncio
async def test_cancel_order_sends_delete_with_order_id(cfg: BingXConfig) -> None:
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        payload = _order_ok_payload(order_id="1001", status="CANCELED")
        route = mock.delete(cfg.rest_endpoints.cancel_order).mock(
            return_value=httpx.Response(200, json=_ok(payload))
        )
        result = await PrivateAPI(client).cancel_order("BTC-USDT", order_id="1001")
    assert result.status == "CANCELED"
    sent = dict(route.calls.last.request.url.params)
    assert sent["orderId"] == "1001"


@pytest.mark.asyncio
async def test_cancel_all_returns_empty_on_nothing_to_cancel(cfg: BingXConfig) -> None:
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        mock.delete(cfg.rest_endpoints.cancel_all_orders).mock(
            return_value=httpx.Response(200, json=_err(80018, "no orders to cancel"))
        )
        result = await PrivateAPI(client).cancel_all("BTC-USDT")
    assert result == []


@pytest.mark.asyncio
async def test_close_position_on_flat_account_returns_none(cfg: BingXConfig) -> None:
    """close_position идемпотентен: на flat-аккаунте — без действия."""
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        mock.delete(cfg.rest_endpoints.cancel_all_orders).mock(
            return_value=httpx.Response(200, json=_ok({"orders": []}))
        )
        mock.get(cfg.rest_endpoints.positions).mock(return_value=httpx.Response(200, json=_ok([])))
        result = await PrivateAPI(client).close_position("BTC-USDT")
    assert result is None


@pytest.mark.asyncio
async def test_close_position_long_sends_sell_reduce_only_market(
    cfg: BingXConfig,
) -> None:
    """close LONG = SELL reduce_only market на полный размер позиции."""
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        mock.delete(cfg.rest_endpoints.cancel_all_orders).mock(
            return_value=httpx.Response(200, json=_ok({"orders": []}))
        )
        mock.get(cfg.rest_endpoints.positions).mock(
            return_value=httpx.Response(
                200,
                json=_ok(
                    [
                        {
                            "symbol": "BTC-USDT",
                            "positionId": "p1",
                            "positionSide": "BOTH",
                            "positionAmt": "0.005",
                            "avgPrice": "62000",
                            "leverage": 3,
                            "unrealizedProfit": "0",
                        }
                    ]
                ),
            )
        )
        place_route = mock.post(cfg.rest_endpoints.place_order).mock(
            return_value=httpx.Response(
                200,
                json=_ok(
                    {
                        "order": {
                            "orderId": "9001",
                            "symbol": "BTC-USDT",
                            "side": "SELL",
                            "positionSide": "BOTH",
                            "type": "MARKET",
                            "status": "FILLED",
                            "price": "0",
                            "origQty": "0.005",
                            "executedQty": "0.005",
                            "time": 1_700_000_000_000,
                            "updateTime": 1_700_000_000_500,
                            "reduceOnly": True,
                        }
                    }
                ),
            )
        )
        result = await PrivateAPI(client).close_position("BTC-USDT")

    assert result is not None
    assert result.side == "SELL"
    sent = dict(place_route.calls.last.request.url.params)
    assert sent["side"] == "SELL"
    assert sent["type"] == "MARKET"
    assert sent["quantity"] == "0.005"
    assert sent["reduceOnly"] == "true"  # one-way (BOTH): reduceOnly валиден
    # close-side не несёт attached SL/TP.
    assert "stopLoss" not in sent
    assert "takeProfit" not in sent


@pytest.mark.asyncio
async def test_close_position_hedge_long_propagates_position_side(
    cfg: BingXConfig,
) -> None:
    """В hedge mode close передаёт positionSide из позиции (LONG/SHORT) и
    НЕ шлёт reduceOnly: BingX отвергает его с code=109400 «In the Hedge
    mode, the 'ReduceOnly' field can not be filled» (найдено живым
    прогоном GTAA-VST на NCSINASDAQ100). Хардкод reduceOnly=true ломал
    close-leg ребаланса на TradFi-перпах (NCSI*/NCCO*/NCFX*)."""
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        mock.delete(cfg.rest_endpoints.cancel_all_orders).mock(
            return_value=httpx.Response(200, json=_ok({"orders": []}))
        )
        mock.get(cfg.rest_endpoints.positions).mock(
            return_value=httpx.Response(
                200,
                json=_ok(
                    [
                        {
                            "symbol": "NCSINASDAQ1002USD-USDT",
                            "positionId": "p2",
                            "positionSide": "LONG",
                            "positionAmt": "0.26",
                            "avgPrice": "28818.84",
                            "leverage": 3,
                            "unrealizedProfit": "0",
                        }
                    ]
                ),
            )
        )
        place_route = mock.post(cfg.rest_endpoints.place_order).mock(
            return_value=httpx.Response(
                200,
                json=_ok(
                    {
                        "order": {
                            "orderId": "9002",
                            "symbol": "NCSINASDAQ1002USD-USDT",
                            "side": "SELL",
                            "positionSide": "LONG",
                            "type": "MARKET",
                            "status": "FILLED",
                            "price": "0",
                            "origQty": "0.26",
                            "executedQty": "0.26",
                            "time": 1_700_000_000_000,
                            "updateTime": 1_700_000_000_500,
                        }
                    }
                ),
            )
        )
        await PrivateAPI(client).close_position("NCSINASDAQ1002USD-USDT")

    sent = dict(place_route.calls.last.request.url.params)
    assert sent["positionSide"] == "LONG", (
        f"hedge mode: должен передаваться positionSide из позиции, got {sent.get('positionSide')}"
    )
    assert sent["side"] == "SELL"
    assert "reduceOnly" not in sent  # hedge mode: поле опущено (иначе 109400)


# ─── 0.D part 2: listenKey CRUD, cancel_all_after, compensating-close ──────


@pytest.mark.asyncio
async def test_create_listen_key_returns_string(cfg: BingXConfig) -> None:
    """Квирк §7 п.34: userDataStream возвращает СЫРОЙ {listenKey: ...}
    без envelope `{code, msg, data}`. Используем `raw_response=True`."""
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        mock.post(cfg.rest_endpoints.user_data_stream).mock(
            return_value=httpx.Response(200, json={"listenKey": "abc123def456"})
        )
        key = await PrivateAPI(client).create_listen_key()
    assert key == "abc123def456"


@pytest.mark.asyncio
async def test_keep_alive_listen_key_sends_put_with_key(cfg: BingXConfig) -> None:
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        route = mock.put(cfg.rest_endpoints.user_data_stream).mock(
            return_value=httpx.Response(200, json=_ok({}))
        )
        await PrivateAPI(client).keep_alive_listen_key("abc123def456")
    params = dict(route.calls.last.request.url.params)
    assert params["listenKey"] == "abc123def456"


@pytest.mark.asyncio
async def test_keep_alive_listen_key_rejects_empty(cfg: BingXConfig) -> None:
    async with BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client:
        with pytest.raises(ValueError, match="listen_key"):
            await PrivateAPI(client).keep_alive_listen_key("")


@pytest.mark.asyncio
async def test_close_listen_key_sends_delete_with_key(cfg: BingXConfig) -> None:
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        route = mock.delete(cfg.rest_endpoints.user_data_stream).mock(
            return_value=httpx.Response(200, json=_ok({}))
        )
        await PrivateAPI(client).close_listen_key("abc123def456")
    params = dict(route.calls.last.request.url.params)
    assert params["listenKey"] == "abc123def456"


@pytest.mark.asyncio
async def test_cancel_all_after_sends_post_with_timeout(cfg: BingXConfig) -> None:
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        route = mock.post(cfg.rest_endpoints.cancel_all_after).mock(
            return_value=httpx.Response(200, json=_ok({}))
        )
        await PrivateAPI(client).cancel_all_after(60_000)
    params = dict(route.calls.last.request.url.params)
    assert int(params["timeOut"]) == 60_000


@pytest.mark.asyncio
async def test_cancel_all_after_rejects_negative(cfg: BingXConfig) -> None:
    async with BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client:
        with pytest.raises(ValueError, match="timeout_ms"):
            await PrivateAPI(client).cancel_all_after(-1)


@pytest.mark.asyncio
async def test_place_order_compensating_close_when_ack_missing_stop_loss(
    cfg: BingXConfig,
) -> None:
    """Если в ack отсутствует поле stopLoss — close_position + OrderRejected.

    Квирк §7 п.36: attached SL возвращается в ack.order.stopLoss как
    stringified JSON. Если поле пусто/отсутствует — BingX не сохранил SL.
    """
    from adapters.bingx.exceptions import OrderRejected

    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        # place_order ack — успех, но stopLoss пустой
        ack_payload = _order_ok_payload()
        ack_payload["order"]["stopLoss"] = ""  # SL пуст
        mock.post(cfg.rest_endpoints.place_order).mock(
            return_value=httpx.Response(200, json=_ok(ack_payload))
        )
        # close_position зовёт cancel_all + get_positions + place_order(close)
        mock.delete(cfg.rest_endpoints.cancel_all_orders).mock(
            return_value=httpx.Response(200, json=_ok({"orders": []}))
        )
        mock.get(cfg.rest_endpoints.positions).mock(
            return_value=httpx.Response(
                200,
                json=_ok(
                    [
                        {
                            "symbol": "BTC-USDT",
                            "positionId": "p1",
                            "positionSide": "BOTH",
                            "positionAmt": "0.001",
                            "avgPrice": "62000",
                            "leverage": 3,
                            "unrealizedProfit": "0",
                        }
                    ]
                ),
            )
        )
        req = OrderRequest(
            symbol="BTC-USDT",
            side="BUY",
            position_side="LONG",
            order_type="MARKET",
            quantity=Decimal("0.001"),
            attached_stop_loss=Decimal("60000"),
        )
        with pytest.raises(OrderRejected, match="without confirmed SL"):
            await PrivateAPI(client).place_order(req)


@pytest.mark.asyncio
async def test_place_order_accepts_ack_with_stop_loss_set(cfg: BingXConfig) -> None:
    """ack с непустым stopLoss → SL подтверждён, OrderRejected не поднимаем."""
    async with (
        BingXClient(cfg, api_key=_TEST_KEY, api_secret=_TEST_SECRET) as client,
        respx.mock(base_url=cfg.active_rest_base) as mock,
    ):
        _stub_server_time(mock, cfg)
        ack_payload = _order_ok_payload()
        ack_payload["order"]["stopLoss"] = (
            '{"type":"STOP_MARKET","stopPrice":60000,"workingType":"MARK_PRICE"}'
        )
        mock.post(cfg.rest_endpoints.place_order).mock(
            return_value=httpx.Response(200, json=_ok(ack_payload))
        )
        req = OrderRequest(
            symbol="BTC-USDT",
            side="BUY",
            position_side="LONG",
            order_type="MARKET",
            quantity=Decimal("0.001"),
            attached_stop_loss=Decimal("60000"),
        )
        ack = await PrivateAPI(client).place_order(req)
        assert ack.has_attached_stop_loss


def test_parse_user_stream_event_returns_none_for_unknown() -> None:
    from adapters.bingx.private_models import parse_user_stream_event

    assert parse_user_stream_event({"e": "UNKNOWN_TYPE"}) is None


def test_parse_user_stream_event_order_trade_update() -> None:
    from adapters.bingx.private_models import OrderUpdateEvent, parse_user_stream_event

    raw = {
        "e": "ORDER_TRADE_UPDATE",
        "E": 1_700_000_000_500,
        "T": 1_700_000_000_499,
        "o": {
            "s": "BTC-USDT",
            "i": 1234567890,
            "c": "my-coid",
            "S": "BUY",
            "o": "MARKET",
            "X": "FILLED",
            "ps": "BOTH",
            "p": "0",
            "q": "0.001",
            "z": "0.001",
            "ap": "62000",
            "sp": None,
            "n": "-0.0001",
            "N": "VST",
            "rp": "0",
            "R": False,
            "x": "TRADE",
        },
    }
    event = parse_user_stream_event(raw)
    assert isinstance(event, OrderUpdateEvent)
    assert event.order_id == "1234567890"
    assert event.status == "FILLED"
    assert event.executed_quantity == Decimal("0.001")
    assert event.execution_type == "TRADE"


def test_parse_user_stream_event_account_update() -> None:
    from adapters.bingx.private_models import (
        AccountUpdateEvent,
        parse_user_stream_event,
    )

    raw = {
        "e": "ACCOUNT_UPDATE",
        "E": 1_700_000_001_000,
        "a": {
            "B": [{"a": "VST", "wb": "99999.5", "cw": "99999.5", "bc": "-0.5"}],
            "P": [
                {
                    "s": "BTC-USDT",
                    "pa": "0.001",
                    "ep": "62000",
                    "cr": "0",
                    "up": "0",
                    "mt": "ISOLATED",
                    "iw": "100",
                    "ps": "BOTH",
                }
            ],
        },
    }
    event = parse_user_stream_event(raw)
    assert isinstance(event, AccountUpdateEvent)
    assert len(event.balances) == 1
    assert event.balances[0].asset == "VST"
    assert event.balances[0].wallet_balance == Decimal("99999.5")
    assert len(event.positions) == 1
    assert event.positions[0].symbol == "BTC-USDT"
    assert event.positions[0].position_amount == Decimal("0.001")
