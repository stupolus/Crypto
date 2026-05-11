"""Приватный API BingX: read + setters (фаза 0.C) + ордера (фаза 0.D part 1).

Принципы:
- ``Decimal`` для всех денежных полей через ``private_models``.
- Локальная валидация (symbol с дефисом, leverage в диапазоне, mode = ISOLATED,
  инварианты OrderRequest) до отправки запроса — экономит rate-limit и даёт
  понятную ошибку.
- ``set_margin_type`` и ``set_position_mode`` — **idempotent**: повторный
  вызов с тем же значением не считается ошибкой.
- ``place_order`` поддерживает атомарный entry+SL/TP через stringified
  JSON в полях ``stopLoss``/``takeProfit`` (квирк §7 п.7 plans/01).
- ``close_position`` — kill switch: сначала ``cancel_all``, потом reduce_only
  market в обратную сторону.

Источник: docs-v3 → USDT-M Perp Futures → Account/Trade Interfaces; см.
бизнес/инструменты-bingx.md §«Особенности API», plans/04 §4, plans/05.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any, Literal

from adapters.bingx.client import BingXClient
from adapters.bingx.config import BingXConfig
from adapters.bingx.exceptions import APIError, InvalidResponseError
from adapters.bingx.private_models import (
    Balance,
    Fill,
    Order,
    OrderAck,
    OrderRequest,
    OrderSide,
    Position,
    PositionSide,
)

# Бизнес-коды BingX для «уже выставлено» — повторный setter idempotent.
# 80012 — задокументированное «No need to switch» для marginType.
# 80014 / 80017 — варианты для других setter'ов; ловим по подстроке тоже.
_IDEMPOTENT_OK_CODES = frozenset({80012, 80014, 80017})
_IDEMPOTENT_HINTS = ("no need", "already", "no change", "не нуж")


def _is_idempotent_ok(err: APIError) -> bool:
    if err.code in _IDEMPOTENT_OK_CODES:
        return True
    msg = err.message.lower()
    return any(hint in msg for hint in _IDEMPOTENT_HINTS)


def _validate_symbol(symbol: str) -> str:
    if "-" not in symbol:
        raise ValueError(f"BingX symbol must contain hyphen, got {symbol!r}")
    return symbol


def _decimal_to_str(value: Decimal) -> str:
    """Decimal → строка для отправки в BingX. ``format(d, 'f')`` убирает
    научную нотацию и сохраняет precision как введено.

    BingX молча усекает значения превышающие precision символа (см. plans/01
    §4.1 п.2). Округление под precision контракта — задача вызывающей стороны
    (стратегии/risk-engine), адаптер не «угадывает».
    """
    return format(value.normalize(), "f")


def _attached_protective(
    *,
    kind: Literal["STOP_MARKET", "TAKE_PROFIT_MARKET"],
    stop_price: Decimal,
    working_type: Literal["MARK_PRICE", "CONTRACT_PRICE", "INDEX_PRICE"],
) -> str:
    """Сериализовать защитный ордер для полей ``stopLoss``/``takeProfit``.

    Квирк §7 п.7 plans/01: BingX принимает эти поля как stringified JSON.
    Пример из docs: ``takeProfit='{"type":"TAKE_PROFIT_MARKET",
    "stopPrice":31968.0,"workingType":"MARK_PRICE"}'``.

    Квирк §7 п.32 plans/01 (подтверждено на VST 2026-05-11): ``stopPrice``
    обязан быть JSON-числом, не строкой. Передача строки даёт
    ``code=109400 "Mismatch type float64 with value string"``. Поэтому
    конвертируем Decimal → float (precision символа = 1 digit для BTC,
    float достаточно; округление под precision — задача стратегии).
    """
    payload: dict[str, Any] = {
        "type": kind,
        "stopPrice": float(stop_price),
        "workingType": working_type,
    }
    return json.dumps(payload, separators=(",", ":"))


def _extract_order_payload(data: Any) -> Any:
    """``POST/DELETE /trade/order`` оборачивает результат в ``{"order": {...}}``."""
    if isinstance(data, dict) and "order" in data and isinstance(data["order"], dict):
        return data["order"]
    # Иногда BingX возвращает order напрямую под data — fallback.
    if isinstance(data, dict) and "orderId" in data:
        return data
    raise InvalidResponseError(
        f"unexpected /trade/order payload shape: {type(data).__name__}"
    )


# BingX-коды и подстроки сообщений, означающие «нечего отменять» — мы
# возвращаем пустой список вместо ошибки, чтобы `close_position` был
# идемпотентен на flat-аккаунте.
_NOTHING_TO_CANCEL_CODES = frozenset({80018, 80020, 109414})
_NOTHING_TO_CANCEL_HINTS = ("no order", "no orders", "not exist", "не найд")


def _is_nothing_to_cancel(err: APIError) -> bool:
    if err.code in _NOTHING_TO_CANCEL_CODES:
        return True
    msg = err.message.lower()
    return any(hint in msg for hint in _NOTHING_TO_CANCEL_HINTS)


class PrivateAPI:
    """Приватный read + setters. Требует ключи в `BingXClient`."""

    # BingX docs-v3: leverage в диапазоне 1..125, реальный cap зависит
    # от символа и приходит из ответа `set_leverage`. Здесь — sanity-check.
    _LEVERAGE_MIN = 1
    _LEVERAGE_MAX = 125

    def __init__(self, client: BingXClient, config: BingXConfig | None = None) -> None:
        self._client = client
        self._config = config or client.config
        self._endpoints = self._config.rest_endpoints

    # ── Read ───────────────────────────────────────────────────────────────

    async def get_balance(self) -> list[Balance]:
        """Все активы аккаунта (USDT-M perpetual)."""
        data = await self._client.request_signed("GET", self._endpoints.balance)
        items = self._as_list(data, endpoint=self._endpoints.balance)
        return [Balance.model_validate(item) for item in items]

    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        """Открытые / нулевые позиции. Без ``symbol`` — все символы."""
        params: dict[str, Any] = {}
        if symbol is not None:
            params["symbol"] = _validate_symbol(symbol)
        data = await self._client.request_signed(
            "GET", self._endpoints.positions, params=params or None
        )
        items = self._as_list(data, endpoint=self._endpoints.positions)
        return [Position.model_validate(item) for item in items]

    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        """Активные ордера. BingX заворачивает ответ в ``{"orders": [...]}``."""
        params: dict[str, Any] = {}
        if symbol is not None:
            params["symbol"] = _validate_symbol(symbol)
        data = await self._client.request_signed(
            "GET", self._endpoints.open_orders, params=params or None
        )
        items = self._unwrap_orders(data)
        return [Order.model_validate(item) for item in items]

    async def get_fills(
        self,
        symbol: str,
        *,
        start_ms: int | None = None,
        end_ms: int | None = None,
        limit: int = 500,
    ) -> list[Fill]:
        """История исполнений по символу.

        Лимит: BingX позволяет до 1000 (docs-v3). Здесь дефолт 500 как
        безопасный шаг для бэктеста.
        """
        _validate_symbol(symbol)
        if limit <= 0 or limit > 1000:
            raise ValueError(f"fills limit must be in 1..1000, got {limit}")
        params: dict[str, Any] = {"symbol": symbol, "limit": limit}
        if start_ms is not None:
            params["startTs"] = start_ms
        if end_ms is not None:
            params["endTs"] = end_ms
        data = await self._client.request_signed(
            "GET", self._endpoints.fills, params=params
        )
        items = self._unwrap_fills(data)
        return [Fill.model_validate(item) for item in items]

    # ── Setters (idempotent) ───────────────────────────────────────────────

    async def set_margin_mode(
        self,
        symbol: str,
        mode: Literal["ISOLATED", "CROSSED"] = "ISOLATED",
    ) -> None:
        """Выставить margin type для символа. ``ISOLATED`` — наш инвариант.

        Idempotent: если режим уже стоит — BingX возвращает ``code=80012``
        («No need to switch»), мы это глотаем как успех.
        """
        _validate_symbol(symbol)
        params = {"symbol": symbol, "marginType": mode}
        try:
            await self._client.request_signed(
                "POST", self._endpoints.set_margin_type, params=params
            )
        except APIError as err:
            if not _is_idempotent_ok(err):
                raise

    async def set_leverage(
        self,
        symbol: str,
        leverage: int,
        side: PositionSide = "BOTH",
    ) -> None:
        """Выставить плечо для символа. Для one-way ``side="BOTH"``."""
        _validate_symbol(symbol)
        if not (self._LEVERAGE_MIN <= leverage <= self._LEVERAGE_MAX):
            raise ValueError(
                f"leverage must be in {self._LEVERAGE_MIN}..{self._LEVERAGE_MAX}, "
                f"got {leverage}"
            )
        params = {"symbol": symbol, "leverage": leverage, "side": side}
        try:
            await self._client.request_signed(
                "POST", self._endpoints.set_leverage, params=params
            )
        except APIError as err:
            if not _is_idempotent_ok(err):
                raise

    async def set_position_mode(self, one_way: bool = True) -> None:
        """Переключить ``one-way`` / ``dual-side`` режим.

        Для one-way (наш инвариант) → ``dualSidePosition="false"``.
        Idempotent: BingX даёт ``code≈80014`` или сообщение «no need» при
        повторном вызове — глотаем как успех.
        """
        # BingX docs-v3 ожидает строковый "true"/"false" в этом параметре —
        # явная стрингификация, не Python bool.
        params = {"dualSidePosition": "false" if one_way else "true"}
        try:
            await self._client.request_signed(
                "POST", self._endpoints.set_position_mode, params=params
            )
        except APIError as err:
            if not _is_idempotent_ok(err):
                raise

    # ── Orders (фаза 0.D part 1) ───────────────────────────────────────────

    async def place_order(self, req: OrderRequest) -> OrderAck:
        """Разместить ордер. Атомарный entry+SL/TP через stringified JSON.

        Защита: на VST разрешено всё; live-запрет — в фазе 1 (явный гейт).
        Сейчас защита от случайного live-запуска делается через `BINGX_ENV`
        в `.env`: пока там `vst`, signed-запросы идут только на VST.
        """
        params: dict[str, Any] = {
            "symbol": req.symbol,
            "side": req.side,
            "positionSide": req.position_side,
            "type": req.order_type,
            "quantity": _decimal_to_str(req.quantity),
        }
        if req.order_type == "LIMIT":
            assert req.price is not None  # см. OrderRequest._check_invariants
            params["price"] = _decimal_to_str(req.price)
            params["timeInForce"] = req.time_in_force
        if req.reduce_only:
            # BingX docs: строковый "true"/"false"; bool на VST = signature mismatch.
            params["reduceOnly"] = "true"
        if req.attached_stop_loss is not None:
            params["stopLoss"] = _attached_protective(
                kind="STOP_MARKET",
                stop_price=req.attached_stop_loss,
                working_type=req.working_type,
            )
        if req.attached_take_profit is not None:
            params["takeProfit"] = _attached_protective(
                kind="TAKE_PROFIT_MARKET",
                stop_price=req.attached_take_profit,
                working_type=req.working_type,
            )
        coid = req.client_order_id or uuid.uuid4().hex[:32]
        # Квирк §7 п.23 plans/01: BingX docs-v3 даёт оба имени, на VST принят
        # `clientOrderID` (как в payload Place Order). Унифицируем.
        params["clientOrderID"] = coid
        data = await self._client.request_signed(
            "POST", self._endpoints.place_order, params=params
        )
        order_obj = _extract_order_payload(data)
        return OrderAck.model_validate(order_obj)

    async def cancel_order(
        self,
        symbol: str,
        *,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> OrderAck:
        """Отменить активный ордер.

        Должен быть указан либо ``order_id`` (BingX-side), либо
        ``client_order_id`` (наш UUID). Оба сразу — допустимо, но избыточно.
        """
        _validate_symbol(symbol)
        if order_id is None and client_order_id is None:
            raise ValueError("provide order_id or client_order_id")
        params: dict[str, Any] = {"symbol": symbol}
        if order_id is not None:
            params["orderId"] = order_id
        if client_order_id is not None:
            params["clientOrderID"] = client_order_id
        data = await self._client.request_signed(
            "DELETE", self._endpoints.cancel_order, params=params
        )
        order_obj = _extract_order_payload(data)
        return OrderAck.model_validate(order_obj)

    async def cancel_all(self, symbol: str) -> list[Order]:
        """Отменить все активные ордера по символу.

        Возвращает список отменённых (включая protective SL/TP, если они
        размещены отдельными ордерами). Если ничего не было — пустой список.
        """
        _validate_symbol(symbol)
        try:
            data = await self._client.request_signed(
                "DELETE",
                self._endpoints.cancel_all_orders,
                params={"symbol": symbol},
            )
        except APIError as err:
            # BingX молча возвращает "no orders to cancel" в одних версиях
            # как code 80018, в других как обычный ответ с пустым списком.
            # Глотаем «нечего отменять» как успех.
            if _is_nothing_to_cancel(err):
                return []
            raise
        return self._extract_orders(data)

    async def close_position(self, symbol: str) -> OrderAck | None:
        """Kill switch: снять защитные ордера и закрыть позицию рыночным
        reduce_only-ордером в обратную сторону.

        Идемпотентно: если позиции нет — возвращает ``None`` без действий.
        Порядок: сначала `cancel_all`, потом `place_order` — чтобы после
        закрытия не остались висящие защитные ордера на ноль-позиции.
        """
        _validate_symbol(symbol)
        await self.cancel_all(symbol)
        positions = await self.get_positions(symbol)
        # На one-way у нас один Position с position_amt; на dual-side — два.
        # Берём первый ненулевой.
        target = next(
            (p for p in positions if p.position_amount != 0), None
        )
        if target is None:
            return None
        # Знак position_amount: положительный → LONG, отрицательный → SHORT.
        close_side: OrderSide = (
            "SELL" if target.position_amount > 0 else "BUY"
        )
        qty = abs(target.position_amount)
        # Инвариант проекта: one-way режим → positionSide всегда BOTH.
        # На VST 2026-05-11: передача LONG/SHORT в one-way даёт
        # code=109400 «PositionSide field can only be set to BOTH».
        close_req = OrderRequest(
            symbol=symbol,
            side=close_side,
            position_side="BOTH",
            order_type="MARKET",
            quantity=qty,
            reduce_only=True,
        )
        return await self.place_order(close_req)

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_orders(data: Any) -> list[Order]:
        """``cancel_all`` отдаёт либо ``{"orders": [...]}``, либо массив,
        либо ``{"success": [...], "failed": [...]}``. Мы возвращаем все
        успешно отменённые.
        """
        items: list[Any] = []
        if isinstance(data, dict):
            if "orders" in data and isinstance(data["orders"], list):
                items = data["orders"]
            elif "success" in data and isinstance(data["success"], list):
                items = data["success"]
            elif not data:
                items = []
            else:
                # Не падаем — записываем пустой результат и идём дальше.
                list_values = [v for v in data.values() if isinstance(v, list)]
                if len(list_values) == 1:
                    items = list_values[0]
        elif isinstance(data, list):
            items = data
        return [Order.model_validate(it) for it in items]

    @staticmethod
    def _as_list(data: Any, *, endpoint: str) -> list[Any]:
        """Многие приватные эндпоинты возвращают список, но иногда
        BingX оборачивает его в ``{<имя>: [...]}``. Извлекаем оба формата.
        """
        if data is None:
            return []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Если ровно один ключ-список — берём его.
            list_values = [v for v in data.values() if isinstance(v, list)]
            if len(list_values) == 1:
                return list_values[0]
            # ``/user/balance`` V3 возвращает один объект, не список —
            # тогда сам объект и есть единственный элемент.
            return [data]
        raise InvalidResponseError(
            f"unexpected payload shape for {endpoint}: {type(data).__name__}"
        )

    @staticmethod
    def _unwrap_orders(data: Any) -> list[Any]:
        """BingX заворачивает openOrders в ``{"orders": [...]}``."""
        if isinstance(data, dict) and "orders" in data:
            orders = data["orders"]
            if not isinstance(orders, list):
                raise InvalidResponseError(
                    f"openOrders.orders must be list, got {type(orders).__name__}"
                )
            return orders
        if isinstance(data, list):
            return data
        raise InvalidResponseError(
            f"unexpected openOrders payload shape: {type(data).__name__}"
        )

    @staticmethod
    def _unwrap_fills(data: Any) -> list[Any]:
        """BingX заворачивает allFillOrders в ``{"fill_history_orders": [...]}``
        или возвращает массив. Поддерживаем оба формата.
        """
        if isinstance(data, dict):
            for key in ("fill_history_orders", "fillHistoryOrders", "fills"):
                value = data.get(key)
                if isinstance(value, list):
                    return list(value)
            # Без знакомого ключа — пытаемся забрать единственный массив.
            list_values: list[list[Any]] = [
                v for v in data.values() if isinstance(v, list)
            ]
            if len(list_values) == 1:
                return list(list_values[0])
            raise InvalidResponseError(
                f"unexpected fills payload keys: {sorted(data.keys())}"
            )
        if isinstance(data, list):
            return data
        raise InvalidResponseError(
            f"unexpected fills payload shape: {type(data).__name__}"
        )
