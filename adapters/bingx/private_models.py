"""Pydantic-модели приватных ответов BingX (USDT-M perpetual).

Все денежные/количественные поля — ``Decimal`` (никаких ``float``). Поля,
которых может не быть в конкретном ответе (например, ``stop_price`` для
market-ордера), помечены ``Optional``. ``extra="ignore"`` — BingX добавляет
поля без анонса (см. ретро 2026-05-10), мы не падаем.

Источники полей: docs-v3 → USDT-M Perp Futures → Account Interfaces /
Trade Interfaces. См. также бизнес/инструменты-bingx.md §«Особенности API».
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _ms_to_utc(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=UTC)


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        str_strip_whitespace=True,
    )


# ─── /user/balance ────────────────────────────────────────────────────────────


class Balance(_StrictModel):
    """Один актив из ``GET /openApi/swap/v3/user/balance``.

    В V3 ``data`` — массив объектов по каждому активу. ``balance`` — общий
    capital, ``available_margin`` — свободно для открытия новых позиций.
    """

    user_id: str | None = Field(default=None, alias="userId")
    asset: str
    balance: Decimal
    equity: Decimal
    unrealized_profit: Decimal = Field(alias="unrealizedProfit")
    realised_profit: Decimal | None = Field(default=None, alias="realisedProfit")
    available_margin: Decimal = Field(alias="availableMargin")
    used_margin: Decimal = Field(alias="usedMargin")
    freezed_margin: Decimal | None = Field(default=None, alias="freezedMargin")


# ─── /user/positions ──────────────────────────────────────────────────────────


PositionSide = Literal["LONG", "SHORT", "BOTH"]
MarginType = Literal["ISOLATED", "CROSSED"]


class Position(_StrictModel):
    """Открытая (или нулевая) позиция из ``GET /openApi/swap/v2/user/positions``.

    Для one-way режима ``position_side="BOTH"``. Для dual-side — ``LONG``/``SHORT``.
    ``position_amount`` может быть 0 — это «слот» без позиции, BingX иногда
    возвращает их в общем списке.
    """

    symbol: str
    position_id: str | None = Field(default=None, alias="positionId")
    position_side: PositionSide = Field(alias="positionSide")
    position_amount: Decimal = Field(alias="positionAmt")
    available_amount: Decimal | None = Field(default=None, alias="availableAmt")
    average_price: Decimal = Field(alias="avgPrice")
    mark_price: Decimal | None = Field(default=None, alias="markPrice")
    leverage: int
    margin_type: MarginType | None = Field(default=None, alias="marginType")
    isolated_margin: Decimal | None = Field(default=None, alias="isolatedMargin")
    unrealized_profit: Decimal = Field(alias="unrealizedProfit")
    realised_profit: Decimal | None = Field(default=None, alias="realisedProfit")
    liquidation_price: Decimal | None = Field(default=None, alias="liquidationPrice")
    update_time_ms: int | None = Field(default=None, alias="updateTime")

    @field_validator("symbol")
    @classmethod
    def _check_hyphen(cls, v: str) -> str:
        if "-" not in v:
            raise ValueError(f"BingX symbol must contain hyphen, got {v!r}")
        return v


# ─── /trade/openOrders & /trade/allFillOrders ─────────────────────────────────


OrderSide = Literal["BUY", "SELL"]
OrderType = Literal[
    "MARKET",
    "LIMIT",
    "STOP_MARKET",
    "STOP",
    "TAKE_PROFIT_MARKET",
    "TAKE_PROFIT",
    "TRIGGER_MARKET",
    "TRIGGER_LIMIT",
]
OrderStatus = Literal[
    "NEW",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELED",
    "EXPIRED",
    "REJECTED",
    "PENDING",
    "WORKING",
]


class Order(_StrictModel):
    """Активный ордер из ``GET /openApi/swap/v2/trade/openOrders``.

    ``stop_price`` присутствует только у stop/trigger ордеров. ``executed_qty``
    + ``avg_price`` могут быть нулями для NEW.
    """

    order_id: str = Field(alias="orderId")
    client_order_id: str | None = Field(default=None, alias="clientOrderID")
    symbol: str
    side: OrderSide
    position_side: PositionSide = Field(alias="positionSide")
    type: OrderType
    status: OrderStatus
    price: Decimal
    original_quantity: Decimal = Field(alias="origQty")
    executed_quantity: Decimal = Field(alias="executedQty")
    average_price: Decimal | None = Field(default=None, alias="avgPrice")
    stop_price: Decimal | None = Field(default=None, alias="stopPrice")
    time_ms: int = Field(alias="time")
    update_time_ms: int = Field(alias="updateTime")
    reduce_only: bool | None = Field(default=None, alias="reduceOnly")

    @field_validator("symbol")
    @classmethod
    def _check_hyphen(cls, v: str) -> str:
        if "-" not in v:
            raise ValueError(f"BingX symbol must contain hyphen, got {v!r}")
        return v

    @property
    def time_utc(self) -> datetime:
        return _ms_to_utc(self.time_ms)

    @property
    def update_time_utc(self) -> datetime:
        return _ms_to_utc(self.update_time_ms)


class Fill(_StrictModel):
    """Исполнение из ``GET /openApi/swap/v2/trade/allFillOrders``.

    ``commission`` отрицательная для taker / положительная для maker-rebate
    (как в BingX-конвенции; знак сохраняем как пришло).
    """

    trade_id: str = Field(alias="tradeId")
    order_id: str = Field(alias="orderId")
    symbol: str
    side: OrderSide
    position_side: PositionSide = Field(alias="positionSide")
    price: Decimal
    quantity: Decimal = Field(alias="qty")
    quote_quantity: Decimal | None = Field(default=None, alias="quoteQty")
    commission: Decimal
    commission_asset: str = Field(alias="commissionAsset")
    realised_profit: Decimal | None = Field(default=None, alias="realisedPNL")
    is_maker: bool = Field(alias="maker")
    time_ms: int = Field(alias="time")

    @field_validator("symbol")
    @classmethod
    def _check_hyphen(cls, v: str) -> str:
        if "-" not in v:
            raise ValueError(f"BingX symbol must contain hyphen, got {v!r}")
        return v

    @property
    def time_utc(self) -> datetime:
        return _ms_to_utc(self.time_ms)
