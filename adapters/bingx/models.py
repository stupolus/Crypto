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


# ─── Приватные модели (фаза 0.C) ─────────────────────────────────────────────
# Источник: docs-v3 JS-бандл, сверка 2026-05-11 (`/tmp/bingx-app.js`).
# Денежные поля — Decimal. Опциональные — там, где BingX возвращает значение
# не во всех окружениях (V2 vs V3, futures vs RWA, hedge vs one-way).


class AssetBalance(_StrictModel):
    """Один элемент массива ``data`` из ``GET /openApi/swap/v3/user/balance``.

    Пример из docs (BTC):
    ``{"userId":"...","asset":"BTC","balance":"0.14438227","equity":"0.14428116",
       "unrealizedProfit":"-0.0001011","availableMargin":"0.14317271",
       "usedMargin":"0.00110845","freezedMargin":"0","shortUid":"12345678"}``

    ``realisedProfit`` присутствует на V2-ответе (USDT-баланс), но отсутствует
    в V3-балансе крипто-активов — отмечаем Optional.
    """

    user_id: str | None = Field(default=None, alias="userId")
    asset: str
    balance: DecimalField
    equity: DecimalField
    unrealized_profit: DecimalField = Field(alias="unrealizedProfit")
    realised_profit: DecimalField | None = Field(default=None, alias="realisedProfit")
    available_margin: DecimalField = Field(alias="availableMargin")
    used_margin: DecimalField = Field(alias="usedMargin")
    freezed_margin: DecimalField = Field(alias="freezedMargin")
    short_uid: str | None = Field(default=None, alias="shortUid")


class Position(_StrictModel):
    """Один элемент ``data`` из ``GET /openApi/swap/v2/user/positions``.

    Поля по примеру из docs-v3:
    ``{"symbol":"BTC-USD","positionId":"...","positionSide":"LONG",
       "isolated":false,"positionAmt":"3","availableAmt":"3",
       "unrealizedProfit":"-0.00010485","initialMargin":"0.00110845",
       "liquidationPrice":2024.78,"avgPrice":"67662","leverage":4,
       "markPrice":"66098.9","riskRate":"0.00013841",
       "maxMarginReduction":"0","updateTime":1718409600901}``

    ``positionAmt`` в one-way mode всегда ≥ 0 и сопровождается ``positionSide``.
    Размер позиции с знаком стратегия определяет сама.
    """

    symbol: str
    position_id: str | None = Field(default=None, alias="positionId")
    position_side: str = Field(alias="positionSide")
    isolated: bool
    position_amt: DecimalField = Field(alias="positionAmt")
    available_amt: DecimalField | None = Field(default=None, alias="availableAmt")
    unrealized_profit: DecimalField = Field(alias="unrealizedProfit")
    initial_margin: DecimalField | None = Field(default=None, alias="initialMargin")
    liquidation_price: DecimalField | None = Field(default=None, alias="liquidationPrice")
    avg_price: DecimalField = Field(alias="avgPrice")
    leverage: int
    mark_price: DecimalField | None = Field(default=None, alias="markPrice")
    risk_rate: DecimalField | None = Field(default=None, alias="riskRate")
    max_margin_reduction: DecimalField | None = Field(default=None, alias="maxMarginReduction")
    update_time_ms: int | None = Field(default=None, alias="updateTime")

    @field_validator("symbol")
    @classmethod
    def _check_hyphen(cls, v: str) -> str:
        if "-" not in v:
            raise ValueError(f"BingX symbol must contain hyphen, got {v!r}")
        return v


class OpenOrder(_StrictModel):
    """Один элемент ``data.orders`` из ``GET /openApi/swap/v2/trade/openOrders``.

    Поля по примеру из docs-v3:
    ``{"symbol":"PYTH-USDT","orderId":...,"side":"SELL","positionSide":"SHORT",
       "type":"LIMIT","origQty":"33","price":"0.3916","executedQty":"33",
       "avgPrice":"0.3916","cumQuote":"13","stopPrice":"","profit":"0.0000",
       "commission":"-0.002585","status":"FILLED","time":1702731418000,
       "updateTime":1702731470000,"clientOrderId":"","leverage":"15X",
       "workingType":"MARK_PRICE","reduceOnly":false, ...}``

    ``stopPrice``/``avgPrice`` BingX отдаёт пустыми строками когда поля
    не применимы — pydantic Decimal-валидатор не съест "" без помощи.
    Поэтому используем ``str`` для этих полей и парсим в Decimal вручную
    через свойства, чтобы оставаться толерантными.
    """

    symbol: str
    order_id: int = Field(alias="orderId")
    side: str
    position_side: str = Field(alias="positionSide")
    type: str
    status: str
    orig_qty: DecimalField = Field(alias="origQty")
    executed_qty: DecimalField = Field(alias="executedQty")
    price: DecimalField
    avg_price: DecimalField = Field(alias="avgPrice")
    cum_quote: DecimalField | None = Field(default=None, alias="cumQuote")
    stop_price: str | None = Field(default=None, alias="stopPrice")
    profit: DecimalField | None = None
    commission: DecimalField | None = None
    client_order_id: str = Field(default="", alias="clientOrderId")
    leverage: str | None = None
    working_type: str | None = Field(default=None, alias="workingType")
    reduce_only: bool | None = Field(default=None, alias="reduceOnly")
    time_ms: int | None = Field(default=None, alias="time")
    update_time_ms: int | None = Field(default=None, alias="updateTime")

    @property
    def stop_price_decimal(self) -> Decimal | None:
        """``stopPrice`` как Decimal или None для пустой строки."""
        if self.stop_price is None or self.stop_price == "":
            return None
        return Decimal(self.stop_price)


class Fill(_StrictModel):
    """Один элемент ``data.fill_orders`` из ``GET /openApi/swap/v2/trade/allFillOrders``.

    Пример:
    ``{"filledTm":"2023-12-16T20:58:36Z","volume":"4.10","price":"3.1088",
       "amount":"12.7492","commission":"-0.0025","currency":"USDT",
       "orderId":"1736007768311123456","liquidatedPrice":"",
       "liquidatedMarginRatio":"","filledTime":"2023-12-16T20:58:36.000+0800",
       "clientOrderId":"","symbol":"WLD-USDT"}``

    ``filledTm`` — строка ISO-8601 UTC; ``filledTime`` — то же время с TZ-offset.
    Адаптер сохраняет обе формы и предоставляет parsed datetime в свойстве.
    """

    symbol: str
    order_id: str = Field(alias="orderId")
    client_order_id: str = Field(default="", alias="clientOrderId")
    volume: DecimalField
    price: DecimalField
    amount: DecimalField
    commission: DecimalField
    currency: str
    filled_tm: str = Field(alias="filledTm")
    filled_time: str | None = Field(default=None, alias="filledTime")
    liquidated_price: str | None = Field(default=None, alias="liquidatedPrice")
    liquidated_margin_ratio: str | None = Field(default=None, alias="liquidatedMarginRatio")

    @property
    def filled_at(self) -> datetime:
        """ISO-8601 UTC из ``filledTm`` в datetime с tz=UTC."""
        # Поддерживаем оба формата, что встречаются в живых данных:
        # "2023-12-16T20:58:36Z" и "2023-12-16T20:58:36.000Z".
        return datetime.fromisoformat(self.filled_tm.replace("Z", "+00:00"))


class PositionMode(_StrictModel):
    """``GET/POST /openApi/swap/v1/positionSide/dual`` ответ.

    Пример: ``{"dualSidePosition": "true"}``  (строка!).
    Адаптер преобразует в bool через свойство — стратегия видит булево.
    """

    dual_side_position: str = Field(alias="dualSidePosition")

    @property
    def is_hedge_mode(self) -> bool:
        return self.dual_side_position.lower() == "true"


class LeverageInfo(_StrictModel):
    """Ответ ``POST /openApi/swap/v2/trade/leverage``.

    Пример из docs-v3 (один из двух известных форматов):
    ``{"symbol":"ETH-USDT","leverage":8}``.

    Другой формат (с разделением long/short, для hedge mode):
    ``{"symbol":"BTC-USD","longLeverage":4,"shortLeverage":8,
       "maxLongLeverage":150,"maxShortLeverage":150,
       "availableLongVol":"15000000","availableShortVol":"15000000"}``

    Все поля опциональные — BingX отдаёт разный набор в зависимости от mode.
    """

    symbol: str
    leverage: int | None = None
    long_leverage: int | None = Field(default=None, alias="longLeverage")
    short_leverage: int | None = Field(default=None, alias="shortLeverage")
    max_long_leverage: int | None = Field(default=None, alias="maxLongLeverage")
    max_short_leverage: int | None = Field(default=None, alias="maxShortLeverage")
    available_long_vol: DecimalField | None = Field(default=None, alias="availableLongVol")
    available_short_vol: DecimalField | None = Field(default=None, alias="availableShortVol")
