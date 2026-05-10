"""Pydantic-модели ответов публичных эндпоинтов BingX (USDT-M perpetual).

Каждая модель ссылается на конкретный эндпоинт docs-v3.
Все денежные/количественные поля — ``Decimal`` (никаких ``float``: точность
платежей и проверки риска не выживет приведений к плавающей точке).

Источники полей зафиксированы в бизнес/инструменты-bingx.md.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _ms_to_utc(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=UTC)


# Pydantic Decimal сам корректно парсит str/int/float, поэтому отдельная
# обёртка не нужна. Алиас даёт типу осмысленное имя в сигнатурах.
DecimalField = Decimal


class _StrictModel(BaseModel):
    """База для всех моделей: запрещаем лишние поля, чтобы расхождение
    схемы было видно в тесте, а не в проде.
    """

    model_config = ConfigDict(
        extra="ignore",  # BingX иногда добавляет поля без анонса — игнорим, не падаем
        frozen=True,
        str_strip_whitespace=True,
    )


class ServerTime(_StrictModel):
    """``GET /openApi/swap/v2/server/time``.

    Тело ответа BingX: ``{"code": 0, "msg": "", "data": {"serverTime": 1234567890123}}``.
    Эта модель — про вложенный ``data``.
    """

    server_time_ms: int = Field(alias="serverTime")

    @property
    def utc(self) -> datetime:
        return _ms_to_utc(self.server_time_ms)


class Contract(_StrictModel):
    """Один элемент массива из ``GET /openApi/swap/v2/quote/contracts``.

    Источник полей: пример ответа docs-v3 (см. бизнес/инструменты-bingx.md
    §«Крипта (USDT-M perpetual)»). ``status=1`` означает торгуется.
    """

    contract_id: str = Field(alias="contractId")
    symbol: str
    asset: str
    currency: str
    quantity_precision: int = Field(alias="quantityPrecision")
    price_precision: int = Field(alias="pricePrecision")
    fee_rate: DecimalField = Field(alias="feeRate")
    maker_fee_rate: DecimalField = Field(alias="makerFeeRate")
    taker_fee_rate: DecimalField = Field(alias="takerFeeRate")
    trade_min_quantity: DecimalField = Field(alias="tradeMinQuantity")
    trade_min_usdt: DecimalField = Field(alias="tradeMinUSDT")
    # max_*_leverage есть в примере ответа docs-v3, но live API их не отдаёт
    # в /openApi/swap/v2/quote/contracts (проверено 2026-05-10 integration-тестом).
    # Реальное плечо берётся через POST /openApi/swap/v2/trade/leverage (фаза 0.C).
    max_long_leverage: int | None = Field(default=None, alias="maxLongLeverage")
    max_short_leverage: int | None = Field(default=None, alias="maxShortLeverage")
    status: int

    @field_validator("symbol")
    @classmethod
    def _check_hyphen(cls, v: str) -> str:
        # Квирк §7 п.1 plans/01: BingX требует дефис в символе.
        if "-" not in v:
            raise ValueError(f"BingX symbol must contain hyphen, got {v!r}")
        return v


class Ticker(_StrictModel):
    """``GET /openApi/swap/v2/quote/ticker`` — 24h-статистика по символу.

    Внутри ``data`` BingX отдаёт объект (не массив для конкретного символа).
    """

    symbol: str
    price_change: DecimalField = Field(alias="priceChange")
    price_change_percent: DecimalField = Field(alias="priceChangePercent")
    last_price: DecimalField = Field(alias="lastPrice")
    last_qty: DecimalField | None = Field(default=None, alias="lastQty")
    open_price: DecimalField = Field(alias="openPrice")
    high_price: DecimalField = Field(alias="highPrice")
    low_price: DecimalField = Field(alias="lowPrice")
    volume: DecimalField
    quote_volume: DecimalField = Field(alias="quoteVolume")
    open_time_ms: int = Field(alias="openTime")
    close_time_ms: int = Field(alias="closeTime")

    @property
    def open_time(self) -> datetime:
        return _ms_to_utc(self.open_time_ms)

    @property
    def close_time(self) -> datetime:
        return _ms_to_utc(self.close_time_ms)


class Kline(_StrictModel):
    """Свеча из ``GET /openApi/swap/v3/quote/klines``.

    Квирк §7 п.11 plans/01: V3 не отдаёт ``n`` (трейды) и ``q`` (turnover).
    Если они нужны — берём через WS-канал ``<symbol>@kline_<interval>``.

    BingX REST V3 возвращает массив объектов с ключами
    ``{"open": "...", "close": "...", "high": "...", "low": "...",
       "volume": "...", "time": <ms>}``.
    """

    open: DecimalField
    high: DecimalField
    low: DecimalField
    close: DecimalField
    volume: DecimalField
    open_time_ms: int = Field(alias="time")

    @property
    def open_time(self) -> datetime:
        return _ms_to_utc(self.open_time_ms)
