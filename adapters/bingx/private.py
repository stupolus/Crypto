"""Приватные read + idempotent setters BingX (фаза 0.C).

Содержит **только** read-методы и setter'ы параметров аккаунта/символа.
Никаких ордеров: ``place_order``, ``cancel_order``, ``close_position`` —
это фаза 0.D, отдельный модуль.

Принципы:
- ``Decimal`` для всех денежных полей через ``private_models``.
- Локальная валидация (symbol с дефисом, leverage в диапазоне, mode = ISOLATED)
  до отправки запроса — экономит rate-limit и даёт понятную ошибку.
- ``set_margin_type`` и ``set_position_mode`` — **idempotent**: повторный
  вызов с тем же значением не считается ошибкой, даже если BingX возвращает
  специальный ``code`` («No need to switch»).
- Все эндпоинты приходят из ``config.yaml`` через ``BingXConfig``, никаких
  хардкод-путей в коде.

Источник: docs-v3 → USDT-M Perp Futures → Account/Trade Interfaces; см.
бизнес/инструменты-bingx.md §«Особенности API», plans/04 §4.
"""

from __future__ import annotations

from typing import Any, Literal

from adapters.bingx.client import BingXClient
from adapters.bingx.config import BingXConfig
from adapters.bingx.exceptions import APIError, InvalidResponseError
from adapters.bingx.private_models import (
    Balance,
    Fill,
    Order,
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

    # ── helpers ────────────────────────────────────────────────────────────

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
