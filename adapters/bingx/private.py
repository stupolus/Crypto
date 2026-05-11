"""Приватные REST-методы BingX (USDT-M perpetual).

Все эндпоинты — подписанные (HMAC-SHA256, header ``X-BX-APIKEY``).
Источники, форматы ответов и квирки — ``plans/01-bingx-адаптер.md`` §3-7,
сверка путей по docs-v3 JS-бандлу 2026-05-11.

Архитектура: ``PrivateAPI`` оборачивает ``BingXClient`` и возвращает
типизированные pydantic-модели. Сам клиент уже умеет подпись + sync
серверного времени (см. ``client.py``).

Фаза 0.C: только read + setters (margin type / leverage / position mode).
Размещение / отмена / закрытие ордеров — фаза 0.D.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from adapters.bingx.client import BingXClient
from adapters.bingx.config import BingXConfig
from adapters.bingx.exceptions import InvalidResponseError
from adapters.bingx.models import (
    AssetBalance,
    Fill,
    LeverageInfo,
    OpenOrder,
    Position,
    PositionMode,
)
from adapters.bingx.public import _normalize_symbol

MarginType = Literal["ISOLATED", "CROSSED"]
LeverageSide = Literal["LONG", "SHORT", "BOTH"]


class PrivateAPI:
    """Приватные эндпоинты BingX, типизированные.

    Требует, чтобы ``BingXClient`` был создан с ``api_key``/``api_secret``;
    иначе любой метод этого класса падает в ``AuthError``.
    """

    def __init__(self, client: BingXClient, config: BingXConfig) -> None:
        self._client = client
        self._cfg = config

    # ── Balance ────────────────────────────────────────────────────────────
    async def get_balance(self) -> list[AssetBalance]:
        """``GET /openApi/swap/v3/user/balance`` — баланс по всем активам.

        V3 возвращает массив (по одному элементу на актив: USDT, BTC, …),
        в отличие от V2 (один объект-USDT). Берём V3, т.к. в фазе 1+ нам
        потребуется multi-asset (RWA-перпы на BTC/ETH margin).
        """
        data = await self._client.request_signed(
            "GET", self._cfg.private_endpoints.balance
        )
        items = _ensure_list(data, "balance")
        return [AssetBalance.model_validate(item) for item in items]

    async def get_usdt_balance(self) -> AssetBalance:
        """Удобный фильтр: эквити USDT-кошелька — основа риск-движка.

        Бросает ``InvalidResponseError`` если USDT не в выдаче (что
        нештатно — BingX всегда возвращает USDT-строку для USDT-M perp).
        """
        for item in await self.get_balance():
            if item.asset.upper() == "USDT":
                return item
        raise InvalidResponseError(
            "USDT asset not found in /user/balance response"
        )

    # ── Positions ──────────────────────────────────────────────────────────
    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        """``GET /openApi/swap/v2/user/positions``.

        ``symbol`` опционален: без него BingX отдаёт все позиции аккаунта.
        В one-way mode на один символ может быть максимум одна позиция;
        в hedge mode — две (LONG + SHORT). Стратегия и risk engine должны
        быть готовы к обоим вариантам, чтобы не упасть после ручного
        переключения mode оператором.
        """
        params: dict[str, Any] = {}
        if symbol is not None:
            params["symbol"] = _normalize_symbol(symbol)
        data = await self._client.request_signed(
            "GET", self._cfg.private_endpoints.positions, params=params
        )
        return [Position.model_validate(item) for item in _ensure_list(data, "positions")]

    # ── Open orders ────────────────────────────────────────────────────────
    async def get_open_orders(self, symbol: str | None = None) -> list[OpenOrder]:
        """``GET /openApi/swap/v2/trade/openOrders``.

        ``data`` обёрнут в ``{"orders": [...]}`` (квирк BingX: единственный из
        list-эндпоинтов с обёрткой). Используется для reconcile после рестарта.
        """
        params: dict[str, Any] = {}
        if symbol is not None:
            params["symbol"] = _normalize_symbol(symbol)
        data = await self._client.request_signed(
            "GET", self._cfg.private_endpoints.open_orders, params=params
        )
        orders = _ensure_dict(data, "open_orders").get("orders", [])
        if not isinstance(orders, list):
            raise InvalidResponseError(
                f"open_orders.orders expected list, got {type(orders).__name__}"
            )
        return [OpenOrder.model_validate(item) for item in orders]

    # ── Fills (history) ────────────────────────────────────────────────────
    async def get_fills(
        self,
        *,
        start_ts_ms: int,
        end_ts_ms: int,
        symbol: str | None = None,
        trading_unit: Literal["COIN", "CONT"] = "COIN",
        order_id: int | None = None,
        currency: str | None = None,
    ) -> list[Fill]:
        """``GET /openApi/swap/v2/trade/allFillOrders`` — история исполнений.

        ``startTs``/``endTs`` обязательны (BingX-квирк: окно лимитировано
        семью днями, превышение → ``code=80014 "the query range is more than seven days"``).
        ``tradingUnit``: ``COIN`` — qty в базовой валюте (BTC, ETH); ``CONT`` —
        в контрактах. По умолчанию COIN, т.к. это согласуется с ``positionAmt``.

        ``data`` обёрнут в ``{"fill_orders": [...]}`` (snake_case в этом
        эндпоинте — ещё один квирк, отличается от camelCase в openOrders).
        """
        params: dict[str, Any] = {
            "startTs": start_ts_ms,
            "endTs": end_ts_ms,
            "tradingUnit": trading_unit,
        }
        if symbol is not None:
            params["symbol"] = _normalize_symbol(symbol)
        if order_id is not None:
            params["orderId"] = order_id
        if currency is not None:
            params["currency"] = currency
        data = await self._client.request_signed(
            "GET", self._cfg.private_endpoints.fills, params=params
        )
        items = _ensure_dict(data, "fills").get("fill_orders", [])
        if not isinstance(items, list):
            raise InvalidResponseError(
                f"fills.fill_orders expected list, got {type(items).__name__}"
            )
        return [Fill.model_validate(item) for item in items]

    # ── Setters (margin type / leverage / position mode) ───────────────────
    async def set_margin_type(self, symbol: str, margin_type: MarginType) -> None:
        """``POST /openApi/swap/v2/trade/marginType``.

        Меняет режим маржи на инструменте. Запрещён ``CROSSED`` нашим
        риск-профилем — приватный API его примет, но invariants-чек в
        ``ensure_invariants`` упадёт. Адаптер не блокирует здесь, чтобы
        не дублировать логику; вызов с CROSSED — это явная человеческая
        ошибка, и пусть инвариант её ловит.

        Response data: ``[]`` на успех (пустой массив, не объект).
        """
        params = {"symbol": _normalize_symbol(symbol), "marginType": margin_type}
        await self._client.request_signed(
            "POST", self._cfg.private_endpoints.set_margin_type, params=params
        )

    async def set_leverage(
        self,
        symbol: str,
        leverage: int,
        *,
        side: LeverageSide = "BOTH",
    ) -> LeverageInfo:
        """``POST /openApi/swap/v2/trade/leverage``.

        Квирк §7 п.6 plans/01: в one-way mode ``side`` ДОЛЖЕН быть
        ``"BOTH"``; в hedge mode — ``"LONG"``/``"SHORT"``. Передача
        ``LONG``/``SHORT`` в one-way → реджект с понятной ошибкой
        от BingX (мы её не маскируем — пусть стратегия чинит конфиг).
        """
        params = {
            "symbol": _normalize_symbol(symbol),
            "side": side,
            "leverage": str(leverage),
        }
        data = await self._client.request_signed(
            "POST", self._cfg.private_endpoints.set_leverage, params=params
        )
        return LeverageInfo.model_validate(_ensure_dict(data, "leverage"))

    async def get_position_mode(self) -> PositionMode:
        """``GET /openApi/swap/v1/positionSide/dual`` — текущий mode (one-way/hedge)."""
        data = await self._client.request_signed(
            "GET", self._cfg.private_endpoints.position_mode
        )
        return PositionMode.model_validate(_ensure_dict(data, "position_mode"))

    async def set_position_mode(self, *, hedge: bool) -> PositionMode:
        """``POST /openApi/swap/v1/positionSide/dual``.

        Квирк §7 п.4 plans/01: BingX требует строку ``"true"``/``"false"``,
        не bool. Менять mode нельзя при наличии открытых позиций или ордеров
        (``code=109401 "user has pending orders or position"``).

        Наш инвариант ``invariants.position_mode = one_way`` → вызываем
        с ``hedge=False`` на старте сессии. Это идемпотентно: если уже
        one-way, BingX просто подтвердит.
        """
        params = {"dualSidePosition": "true" if hedge else "false"}
        data = await self._client.request_signed(
            "POST", self._cfg.private_endpoints.position_mode, params=params
        )
        return PositionMode.model_validate(_ensure_dict(data, "position_mode"))

    # ── Bootstrap инвариантов ──────────────────────────────────────────────
    async def ensure_invariants(self, symbol: str, leverage: int) -> None:
        """Привести аккаунт к жёстким инвариантам риск-профиля.

        Делает три POST-вызова идемпотентно:
        1. ``position_mode = one_way`` (из ``invariants.position_mode``).
        2. ``margin_type = ISOLATED`` для целевого символа.
        3. ``leverage`` для символа (``side="BOTH"`` в one-way).

        Запускать после создания клиента и до любых ордеров. На VST/live
        BingX вернёт ошибку, если есть открытые позиции/ордера при смене
        ``position_mode`` — это правильно, в этом случае оператор должен
        вручную всё закрыть.
        """
        target_mode_hedge = self._cfg.invariants.position_mode != "one_way"
        await self.set_position_mode(hedge=target_mode_hedge)
        await self.set_margin_type(symbol, self._cfg.invariants.margin_type)
        await self.set_leverage(symbol, leverage, side="BOTH")


# ── Хелперы ────────────────────────────────────────────────────────────────


def _ensure_dict(data: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise InvalidResponseError(
            f"BingX {where} expected object, got {type(data).__name__}: {data!r}"
        )
    return data


def _ensure_list(data: Any, where: str) -> list[Any]:
    if not isinstance(data, list):
        raise InvalidResponseError(
            f"BingX {where} expected list, got {type(data).__name__}: {data!r}"
        )
    return data
