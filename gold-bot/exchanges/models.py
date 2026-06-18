"""Доменные модели для адаптеров бирж gold-bot.

Все денежные/количественные значения — Decimal, никогда float.

Ключевой инвариант (CLAUDE.md §6, risk-profile.md): OrderRequest невозможно
создать без stop_price и в режиме cross-маржи. Запрет — на уровне валидации
модели, не дисциплины: вышестоящий код физически не может сформировать голый
вход без стопа.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class MarginMode(StrEnum):
    ISOLATED = "isolated"
    CROSS = "cross"


class PositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class OrderStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class _Frozen(BaseModel):
    """Базовая неизменяемая модель-значение. Лишние поля биржи игнорируем."""

    model_config = ConfigDict(frozen=True, extra="ignore")


class OHLCV(_Frozen):
    timestamp: int  # ms epoch, время открытия свечи
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class Ticker(_Frozen):
    symbol: str
    last: Decimal
    bid: Decimal
    ask: Decimal
    quote_volume_24h: Decimal
    timestamp: int

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def spread_pct(self) -> Decimal:
        mid = (self.ask + self.bid) / 2
        if mid == 0:
            return Decimal(0)
        return (self.ask - self.bid) / mid


class Balance(_Frozen):
    asset: str
    free: Decimal
    used: Decimal
    total: Decimal


class Position(_Frozen):
    symbol: str
    side: PositionSide
    size: Decimal  # в базовом активе/контрактах, > 0
    entry_price: Decimal
    mark_price: Decimal
    leverage: Decimal
    margin_mode: MarginMode
    unrealized_pnl: Decimal
    liquidation_price: Decimal | None = None


class OrderRequest(_Frozen):
    """Запрос на постановку ордера.

    Создание невозможно:
    - без stop_price (инвариант «стоп — часть входа»);
    - в cross-режиме (инвариант «только изолированная маржа»).

    Для LIMIT-ордера, когда цена входа известна, дополнительно проверяется
    что стоп стоит на защитной стороне. Для MARKET цена входа неизвестна
    заранее — корректность стопа относительно факт. цены проверяет RiskEngine.
    """

    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal = Field(gt=0)
    stop_price: Decimal = Field(gt=0)
    price: Decimal | None = None
    margin_mode: MarginMode = MarginMode.ISOLATED
    reduce_only: bool = False
    client_order_id: str | None = None

    @model_validator(mode="after")
    def _check_invariants(self) -> OrderRequest:
        if self.margin_mode is not MarginMode.ISOLATED:
            raise ValueError("cross-маржа запрещена (CLAUDE.md §6): только isolated")

        if self.order_type is OrderType.LIMIT and self.price is None:
            raise ValueError("LIMIT-ордер требует price")
        if self.order_type is OrderType.MARKET and self.price is not None:
            raise ValueError("MARKET-ордер не принимает price")

        ref = self.price
        if ref is not None:
            if self.side is OrderSide.BUY and self.stop_price >= ref:
                raise ValueError("для BUY stop_price должен быть ниже цены входа")
            if self.side is OrderSide.SELL and self.stop_price <= ref:
                raise ValueError("для SELL stop_price должен быть выше цены входа")
        return self


class OrderResult(_Frozen):
    order_id: str
    symbol: str
    status: OrderStatus
    filled_quantity: Decimal = Decimal(0)
    average_price: Decimal | None = None
    client_order_id: str | None = None
