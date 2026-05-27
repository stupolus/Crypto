"""Тесты PrivateAPI Bybit V5 через respx: balance, positions, orders.

Live-trade блокировка (env=live) тестируется отдельно — не идём в сеть.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from adapters.bingx.private_models import OrderRequest
from adapters.bybit.client import BybitClient
from adapters.bybit.private import PrivateAPI
from adapters.bybit.settings import BybitSettings

_TESTNET_URL = "https://api-testnet.bybit.com"


def _testnet_settings() -> BybitSettings:
    """Settings с testnet-ключами для signed-вызовов."""
    return BybitSettings(
        _env_file=None,
        env="testnet",
        testnet_api_key="k",
        testnet_api_secret="s",
    )


def _ok(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": result,
        "retExtInfo": {},
        "time": 1700000000000,
    }


# ── balance ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_balance_unified() -> None:
    payload = _ok(
        {
            "list": [
                {
                    "accountType": "UNIFIED",
                    "coin": [
                        {
                            "coin": "USDT",
                            "equity": "10000.0",
                            "walletBalance": "9800.0",
                            "availableToWithdraw": "9500.0",
                        },
                        {
                            "coin": "BTC",
                            "equity": "0.1",
                            "walletBalance": "0.1",
                        },
                    ],
                }
            ]
        }
    )
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.get("/v5/account/wallet-balance").mock(return_value=httpx.Response(200, json=payload))
        async with BybitClient(settings=_testnet_settings()) as c:
            balances = await PrivateAPI(c).get_balance()
    coins = {b.coin: b for b in balances}
    assert coins["USDT"].equity == Decimal("10000.0")
    assert coins["BTC"].equity == Decimal("0.1")


@pytest.mark.asyncio
async def test_get_balance_empty_returns_list() -> None:
    """Bybit может вернуть пустой list — get_balance() == []."""
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.get("/v5/account/wallet-balance").mock(
            return_value=httpx.Response(200, json=_ok({"list": []}))
        )
        async with BybitClient(settings=_testnet_settings()) as c:
            assert await PrivateAPI(c).get_balance() == []


# ── positions ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_positions_filters_empty_slots() -> None:
    """В hedge-mode Bybit отдаёт пустые слоты — фильтруем по size>0."""
    payload = _ok(
        {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "size": "0.5",
                    "positionIdx": 1,
                    "entryPrice": "30000",
                    "avgPrice": "30000",
                },
                {
                    "symbol": "BTCUSDT",
                    "side": "",
                    "size": "0",
                    "positionIdx": 2,
                    "avgPrice": "0",
                },
            ]
        }
    )
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        route = mock.get("/v5/position/list").mock(return_value=httpx.Response(200, json=payload))
        async with BybitClient(settings=_testnet_settings()) as c:
            poss = await PrivateAPI(c).get_positions("BTC-USDT")
        # Параметры запроса: category=linear, symbol=BTCUSDT (без дефиса).
        url = str(route.calls.last.request.url)
        assert "category=linear" in url
        assert "symbol=BTCUSDT" in url
    assert len(poss) == 1
    assert poss[0].position_idx == 1
    assert poss[0].position_amount == Decimal("0.5")  # LONG


# ── place_order ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_place_order_market_long_serializes_correctly() -> None:
    """MARKET LONG → side=Buy, positionIdx=1, stopLoss-поле проставлено."""
    captured: dict[str, Any] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json=_ok({"orderId": "100500", "orderLinkId": "coid-001"}),
        )

    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.post("/v5/order/create").mock(side_effect=capture)
        async with BybitClient(settings=_testnet_settings()) as c:
            req = OrderRequest(
                symbol="BTC-USDT",
                side="BUY",
                position_side="LONG",
                order_type="MARKET",
                quantity=Decimal("0.01"),
                attached_stop_loss=Decimal("29000"),
                client_order_id="coid-001",
            )
            ack = await PrivateAPI(c).place_order(req)
    assert ack.order_id == "100500"
    assert ack.order_link_id == "coid-001"
    # body — Bybit-формат:
    assert captured["category"] == "linear"
    assert captured["symbol"] == "BTCUSDT"
    assert captured["side"] == "Buy"
    assert captured["orderType"] == "Market"
    assert captured["positionIdx"] == 1
    assert captured["qty"] == "0.01"
    assert captured["stopLoss"] == "29000"
    assert captured["slTriggerBy"] == "MarkPrice"
    assert captured["orderLinkId"] == "coid-001"
    # Для hedge (positionIdx=1) reduceOnly НЕ шлём:
    assert "reduceOnly" not in captured


@pytest.mark.asyncio
async def test_place_order_limit_short_with_tp() -> None:
    captured: dict[str, Any] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(200, json=_ok({"orderId": "1", "orderLinkId": "x"}))

    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.post("/v5/order/create").mock(side_effect=capture)
        async with BybitClient(settings=_testnet_settings()) as c:
            req = OrderRequest(
                symbol="ETH-USDT",
                side="SELL",
                position_side="SHORT",
                order_type="LIMIT",
                quantity=Decimal("0.1"),
                price=Decimal("3500"),
                attached_stop_loss=Decimal("3600"),
                attached_take_profit=Decimal("3300"),
                time_in_force="IOC",
            )
            await PrivateAPI(c).place_order(req)
    assert captured["side"] == "Sell"
    assert captured["orderType"] == "Limit"
    assert captured["positionIdx"] == 2
    assert captured["price"] == "3500"
    assert captured["timeInForce"] == "IOC"
    assert captured["stopLoss"] == "3600"
    assert captured["takeProfit"] == "3300"
    assert captured["symbol"] == "ETHUSDT"


@pytest.mark.asyncio
async def test_place_order_live_env_blocked() -> None:
    """Hard-guard: env=live → RuntimeError, в сеть не идём."""
    settings = BybitSettings(
        _env_file=None,
        env="live",
        live_api_key="k",
        live_api_secret="s",
    )
    async with BybitClient(settings=settings) as c:
        req = OrderRequest(
            symbol="BTC-USDT",
            side="BUY",
            position_side="LONG",
            order_type="MARKET",
            quantity=Decimal("0.01"),
            attached_stop_loss=Decimal("29000"),
        )
        with pytest.raises(RuntimeError, match="блокирован до фазы 49.5"):
            await PrivateAPI(c).place_order(req)


# ── cancel ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_order_by_id() -> None:
    captured: dict[str, Any] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(json.loads(request.content))
        return httpx.Response(200, json=_ok({"orderId": "1", "orderLinkId": ""}))

    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.post("/v5/order/cancel").mock(side_effect=capture)
        async with BybitClient(settings=_testnet_settings()) as c:
            await PrivateAPI(c).cancel_order("BTC-USDT", order_id="1234")
    assert captured["orderId"] == "1234"
    assert captured["symbol"] == "BTCUSDT"
    assert captured["category"] == "linear"


@pytest.mark.asyncio
async def test_cancel_order_requires_id_or_link_id() -> None:
    async with BybitClient(settings=_testnet_settings()) as c:
        with pytest.raises(ValueError, match="order_id or order_link_id"):
            await PrivateAPI(c).cancel_order("BTC-USDT")


@pytest.mark.asyncio
async def test_cancel_all_returns_empty_on_flat() -> None:
    """Пустой list → возвращаем []."""
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.post("/v5/order/cancel-all").mock(
            return_value=httpx.Response(200, json=_ok({"list": []}))
        )
        async with BybitClient(settings=_testnet_settings()) as c:
            assert await PrivateAPI(c).cancel_all("BTC-USDT") == []


# ── close_position ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_close_position_on_flat_returns_empty() -> None:
    """Idempotent: get_positions пустые → close = []."""
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.get("/v5/position/list").mock(return_value=httpx.Response(200, json=_ok({"list": []})))
        async with BybitClient(settings=_testnet_settings()) as c:
            assert await PrivateAPI(c).close_position("BTC-USDT") == []


@pytest.mark.asyncio
async def test_close_position_hedge_long_uses_opposite_side_same_idx() -> None:
    """LONG hedge-позиция → SELL с тем же positionIdx, БЕЗ reduceOnly."""
    positions_payload = _ok(
        {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "size": "0.5",
                    "positionIdx": 1,
                    "avgPrice": "30000",
                }
            ]
        }
    )
    close_body: dict[str, Any] = {}

    def capture_create(request: httpx.Request) -> httpx.Response:
        import json

        close_body.update(json.loads(request.content))
        return httpx.Response(200, json=_ok({"orderId": "999", "orderLinkId": ""}))

    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.get("/v5/position/list").mock(return_value=httpx.Response(200, json=positions_payload))
        mock.post("/v5/order/create").mock(side_effect=capture_create)
        async with BybitClient(settings=_testnet_settings()) as c:
            acks = await PrivateAPI(c).close_position("BTC-USDT")
    assert len(acks) == 1
    assert acks[0].order_id == "999"
    assert close_body["side"] == "Sell"
    assert close_body["positionIdx"] == 1  # тот же слот
    assert close_body["qty"] == "0.5"
    assert close_body["orderType"] == "Market"
    # Hedge → reduceOnly НЕ шлём (Bybit 109400):
    assert "reduceOnly" not in close_body


@pytest.mark.asyncio
async def test_close_position_one_way_sends_reduce_only() -> None:
    """One-way (positionIdx=0) → reduceOnly=True допустимо и нужно."""
    positions_payload = _ok(
        {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "size": "0.5",
                    "positionIdx": 0,
                    "avgPrice": "30000",
                }
            ]
        }
    )
    close_body: dict[str, Any] = {}

    def capture_create(request: httpx.Request) -> httpx.Response:
        import json

        close_body.update(json.loads(request.content))
        return httpx.Response(200, json=_ok({"orderId": "1", "orderLinkId": ""}))

    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.get("/v5/position/list").mock(return_value=httpx.Response(200, json=positions_payload))
        mock.post("/v5/order/create").mock(side_effect=capture_create)
        async with BybitClient(settings=_testnet_settings()) as c:
            await PrivateAPI(c).close_position("BTC-USDT")
    assert close_body["positionIdx"] == 0
    assert close_body["reduceOnly"] is True
