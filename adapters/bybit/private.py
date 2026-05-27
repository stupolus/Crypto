"""Bybit V5 private API: balance, positions, orders.

Использует общий проектный ``OrderRequest`` из
``adapters.bingx.private_models`` — стратегии exchange-agnostic
(см. план 49 «адаптеры разные, OrderRequest общий»).

Bybit-маппинг полей:
- ``side`` BUY/SELL → ``Buy``/``Sell``
- ``position_side`` LONG/SHORT/BOTH → ``positionIdx`` 1/2/0
- ``order_type`` MARKET/LIMIT → ``Market``/``Limit``
- ``client_order_id`` → ``orderLinkId``
- ``attached_stop_loss`` → ``stopLoss``
- ``attached_take_profit`` → ``takeProfit``
- ``reduce_only`` → ``reduceOnly`` (валидно ТОЛЬКО в one-way, positionIdx=0)
- ``closes_position`` = True семантика: не шлём reduceOnly в hedge —
  закрытие задаётся positionIdx + противоположным side, как у BingX.

⚠️ Live-trade hard-блокируется до фазы 49.5 (план 49). Сейчас signed-
вызовы работают только на testnet (env != "testnet" → RuntimeError).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from adapters.bingx.private_models import OrderRequest
from adapters.bybit.client import BybitClient
from adapters.bybit.private_models import (
    CoinBalance,
    OrderAck,
    Position,
    order_type_to_bybit,
    position_side_to_idx,
    side_to_bybit,
)
from adapters.bybit.symbol import from_project_format

logger = logging.getLogger(__name__)

_CATEGORY = "linear"


def _decimal_str(value: Decimal) -> str:
    """Bybit принимает числа как строки; держим точность Decimal.

    Срезаем нули ТОЛЬКО после десятичной точки (3500 остаётся 3500,
    0.01000 → 0.01, 50.0 → 50).
    """
    s = format(value, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


class PrivateAPI:
    """Высокоуровневые signed-эндпоинты Bybit V5.

    Все методы требуют ``BybitClient.settings.has_credentials() == True``.
    Live-trade на ``env=live`` блокируется на уровне place_order до фазы 49.5.
    """

    def __init__(self, client: BybitClient) -> None:
        self._client = client

    # ── Balance ──────────────────────────────────────────────────────────────

    async def get_balance(self, account_type: str = "UNIFIED") -> list[CoinBalance]:
        """Баланс по монетам. UNIFIED = объединённый кошелёк (default V5).

        Эндпоинт: GET /v5/account/wallet-balance.
        """
        data = await self._client.signed_get(
            "/v5/account/wallet-balance", params={"accountType": account_type}
        )
        lst = data.get("list") or []
        if not lst:
            return []
        # result.list[0].coin = [{coin, equity, walletBalance, ...}, ...]
        coins_raw = lst[0].get("coin") or []
        return [CoinBalance(**c) for c in coins_raw]

    # ── Positions ────────────────────────────────────────────────────────────

    async def get_positions(self, symbol: str) -> list[Position]:
        """Открытые позиции по символу (project-format ``BTC-USDT``).

        Bybit отдаёт пустые слоты для hedge-mode (side=""); фильтруем.
        Эндпоинт: GET /v5/position/list.
        """
        params = {
            "category": _CATEGORY,
            "symbol": from_project_format(symbol),
        }
        data = await self._client.signed_get("/v5/position/list", params=params)
        lst = data.get("list") or []
        positions = [Position(**p) for p in lst]
        # Фильтрация пустых слотов (size = 0 — Bybit отдаёт slots в hedge).
        return [p for p in positions if p.size != 0]

    # ── Orders ───────────────────────────────────────────────────────────────

    async def place_order(self, request: OrderRequest) -> OrderAck:
        """Разместить ордер. SL/TP подмешиваются в тело запроса.

        Live-trade блокируется на env=live до фазы 49.5 (план 49).

        Эндпоинт: POST /v5/order/create.
        """
        # Hard-guard live-trade (план 49.5 снимет; до этого — testnet only).
        if self._client._settings.env == "live":
            raise RuntimeError(
                "Bybit live-trade блокирован до фазы 49.5 (план 49). "
                "Сейчас разрешён только env=testnet для signed-вызовов. "
                "Для read-only public — используй PublicAPI."
            )

        body = self._order_body(request)
        data = await self._client.signed_post("/v5/order/create", body=body)
        return OrderAck(**data)

    async def cancel_order(
        self,
        symbol: str,
        *,
        order_id: str | None = None,
        order_link_id: str | None = None,
    ) -> OrderAck:
        """Отменить ордер по id или client_id (orderLinkId).

        Эндпоинт: POST /v5/order/cancel.
        """
        if not order_id and not order_link_id:
            raise ValueError("cancel_order requires order_id or order_link_id")
        body: dict[str, Any] = {
            "category": _CATEGORY,
            "symbol": from_project_format(symbol),
        }
        if order_id:
            body["orderId"] = order_id
        if order_link_id:
            body["orderLinkId"] = order_link_id
        data = await self._client.signed_post("/v5/order/cancel", body=body)
        return OrderAck(**data)

    async def cancel_all(self, symbol: str | None = None) -> list[OrderAck]:
        """Отменить все ордера (опционально по символу).

        Эндпоинт: POST /v5/order/cancel-all.
        Возвращает список (Bybit отдаёт result.list).
        """
        body: dict[str, Any] = {"category": _CATEGORY}
        if symbol:
            body["symbol"] = from_project_format(symbol)
        data = await self._client.signed_post("/v5/order/cancel-all", body=body)
        lst = data.get("list") or []
        return [OrderAck(**item) for item in lst]

    async def close_position(self, symbol: str) -> list[OrderAck]:
        """Закрыть все позиции по символу (hedge-aware).

        Алгоритм: get_positions → для каждой ненулевой позиции
        place MARKET с противоположным side и тем же positionIdx (hedge:
        positionIdx сохраняет «слот», reduceOnly НЕ шлём; one-way: ставим
        reduceOnly=True).

        Идемпотентно: на flat-аккаунте возвращает [].
        """
        positions = await self.get_positions(symbol)
        if not positions:
            return []

        acks: list[OrderAck] = []
        for pos in positions:
            close_side_bybit = "Sell" if pos.side == "Buy" else "Buy"
            one_way = pos.position_idx == 0
            body: dict[str, Any] = {
                "category": _CATEGORY,
                "symbol": from_project_format(symbol),
                "side": close_side_bybit,
                "orderType": "Market",
                "qty": _decimal_str(pos.size),
                "positionIdx": pos.position_idx,
            }
            if one_way:
                body["reduceOnly"] = True
            data = await self._client.signed_post("/v5/order/create", body=body)
            acks.append(OrderAck(**data))
        return acks

    # ── Internal ─────────────────────────────────────────────────────────────

    def _order_body(self, req: OrderRequest) -> dict[str, Any]:
        """OrderRequest → Bybit V5 POST body для /v5/order/create."""
        body: dict[str, Any] = {
            "category": _CATEGORY,
            "symbol": from_project_format(req.symbol),
            "side": side_to_bybit(req.side),
            "orderType": order_type_to_bybit(req.order_type),
            "qty": _decimal_str(req.quantity),
            "positionIdx": position_side_to_idx(req.position_side),
        }
        if req.order_type == "LIMIT":
            assert req.price is not None  # инвариант OrderRequest
            body["price"] = _decimal_str(req.price)
            body["timeInForce"] = req.time_in_force  # GTC/IOC/FOK
        if req.client_order_id is not None:
            body["orderLinkId"] = req.client_order_id
        # Attached SL/TP — только для entry, не для close.
        if req.attached_stop_loss is not None:
            body["stopLoss"] = _decimal_str(req.attached_stop_loss)
            body["slTriggerBy"] = "MarkPrice"
        if req.attached_take_profit is not None:
            body["takeProfit"] = _decimal_str(req.attached_take_profit)
            body["tpTriggerBy"] = "MarkPrice"
        # reduceOnly — только в one-way (positionIdx=0), как у BingX.
        if req.reduce_only and body["positionIdx"] == 0:
            body["reduceOnly"] = True
        return body
