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

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


# ─── Подтверждение ордера (POST/DELETE /trade/order) ────────────────────────


class OrderAck(_StrictModel):
    """Уплощённый ответ ``POST/DELETE /openApi/swap/v2/trade/order``.

    Квирк live VST 2026-05-11: BingX отдаёт здесь короткий ack, отличный от
    `Order`. Гарантированы только ``orderId``, ``symbol``, ``status``,
    ``side``, ``positionSide``, ``type``. Остальное опционально и зависит от
    типа ордера / стадии исполнения. ``orderId`` приходит как ``int``
    (BingX snowflake-id), мы кастуем в ``str`` для единообразия с `Order`.
    """

    order_id: str = Field(alias="orderId")
    client_order_id: str | None = Field(default=None, alias="clientOrderID")
    symbol: str
    side: OrderSide
    position_side: PositionSide = Field(alias="positionSide")
    type: OrderType
    status: OrderStatus
    price: Decimal | None = None
    stop_price: Decimal | None = Field(default=None, alias="stopPrice")
    original_quantity: Decimal | None = Field(default=None, alias="origQty")
    executed_quantity: Decimal | None = Field(default=None, alias="executedQty")
    average_price: Decimal | None = Field(default=None, alias="avgPrice")
    reduce_only: bool | None = Field(default=None, alias="reduceOnly")
    time_ms: int | None = Field(default=None, alias="time")
    update_time_ms: int | None = Field(default=None, alias="updateTime")

    @field_validator("order_id", mode="before")
    @classmethod
    def _coerce_order_id_to_str(cls, v: object) -> str:
        # BingX отдаёт `orderId` как int (snowflake); кастуем в str для
        # единого контракта с `Order`.
        return str(v)

    @field_validator("symbol")
    @classmethod
    def _check_hyphen(cls, v: str) -> str:
        if "-" not in v:
            raise ValueError(f"BingX symbol must contain hyphen, got {v!r}")
        return v


# ─── Запрос на размещение ордера (наша доменная модель) ──────────────────────


TimeInForce = Literal["GTC", "IOC", "FOK"]
EntryOrderType = Literal["MARKET", "LIMIT"]


class OrderRequest(_StrictModel):
    """Запрос на размещение ордера: наша модель, не от BingX.

    Инвариант проекта (см. plans/01 §3 «Защитные инварианты»): нельзя
    открывать позицию без attached stop_loss. Адаптер запрещает это на
    уровне валидатора, до отправки запроса.

    Для close-side (``reduce_only=True``) attached SL/TP запрещены: позиция
    уже существует, защитные ордера ставятся на entry или отдельным вызовом
    в фазе 0.D part 2.
    """

    symbol: str
    side: OrderSide
    position_side: PositionSide = "BOTH"
    order_type: EntryOrderType
    quantity: Decimal
    price: Decimal | None = None
    reduce_only: bool = False
    time_in_force: TimeInForce = "GTC"
    attached_stop_loss: Decimal | None = None
    attached_take_profit: Decimal | None = None
    client_order_id: str | None = None
    working_type: Literal["MARK_PRICE", "CONTRACT_PRICE", "INDEX_PRICE"] = "MARK_PRICE"

    @field_validator("symbol")
    @classmethod
    def _check_hyphen_req(cls, v: str) -> str:
        if "-" not in v:
            raise ValueError(f"BingX symbol must contain hyphen, got {v!r}")
        return v

    @field_validator("quantity")
    @classmethod
    def _check_positive_quantity(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError(f"quantity must be > 0, got {v}")
        return v

    @field_validator("client_order_id")
    @classmethod
    def _check_client_order_id_length(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not (1 <= len(v) <= 40):
            raise ValueError(
                f"client_order_id length must be 1..40 chars, got {len(v)}"
            )
        return v

    @model_validator(mode="after")
    def _check_invariants(self) -> OrderRequest:
        if self.order_type == "LIMIT" and self.price is None:
            raise ValueError("LIMIT order requires price")
        if self.order_type == "MARKET" and self.price is not None:
            raise ValueError("MARKET order must not have price")
        if self.reduce_only:
            if self.attached_stop_loss is not None:
                raise ValueError("reduce_only order must not carry attached stop_loss")
            if self.attached_take_profit is not None:
                raise ValueError("reduce_only order must not carry attached take_profit")
        else:
            if self.attached_stop_loss is None:
                raise ValueError(
                    "entry order must have attached_stop_loss "
                    "(see бизнес/риск-профиль.md: «нет стопа на бирже — нет позиции»)"
                )
        for fname in ("price", "attached_stop_loss", "attached_take_profit"):
            val = getattr(self, fname)
            if val is not None and val <= 0:
                raise ValueError(f"{fname} must be > 0, got {val}")
        return self
