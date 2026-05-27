"""Public-модели Bybit V5 (klines, тикеры).

Bybit V5 возвращает klines как массив строк (см. документацию
`/v5/market/kline`):
``[start_ms, open, high, low, close, volume, turnover]``.

Тикеры (`/v5/market/tickers?category=linear`) — JSON-объекты с полями
``lastPrice``, ``markPrice``, ``indexPrice``, ``openInterest``, ...
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    """Запрещаем неизвестные поля — ловим API-дрифт сразу."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Kline(_StrictModel):
    """OHLCV-свеча Bybit V5.

    Bybit отдаёт klines в порядке DESC (новый → старый); каллер при
    необходимости разворачивает в ASC.
    """

    start_ms: int  # timestamp начала бара
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    turnover: Decimal

    @classmethod
    def from_v5_row(cls, row: list[str]) -> Kline:
        """Разобрать строку `[start_ms, open, high, low, close, volume, turnover]`.

        Bybit возвращает все числа как **строки** (даже start_ms) —
        кастуем явно.
        """
        if len(row) != 7:
            raise ValueError(f"V5 kline row must have 7 fields, got {len(row)}: {row}")
        return cls(
            start_ms=int(row[0]),
            open=Decimal(row[1]),
            high=Decimal(row[2]),
            low=Decimal(row[3]),
            close=Decimal(row[4]),
            volume=Decimal(row[5]),
            turnover=Decimal(row[6]),
        )


class Ticker(_StrictModel):
    """Snapshot тикера. Поля по Bybit V5 `linear` (USDT-perp)."""

    symbol: str
    last_price: Decimal = Field(alias="lastPrice")
    mark_price: Decimal = Field(alias="markPrice")
    index_price: Decimal = Field(alias="indexPrice")
    open_interest: Decimal | None = Field(default=None, alias="openInterest")
    funding_rate: Decimal | None = Field(default=None, alias="fundingRate")
    bid1_price: Decimal | None = Field(default=None, alias="bid1Price")
    ask1_price: Decimal | None = Field(default=None, alias="ask1Price")
    volume_24h: Decimal | None = Field(default=None, alias="volume24h")
    turnover_24h: Decimal | None = Field(default=None, alias="turnover24h")

    model_config = ConfigDict(
        extra="ignore",  # Bybit добавляет поля — игнорируем, не падаем.
        frozen=True,
        populate_by_name=True,
    )
