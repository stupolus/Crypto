"""Pydantic-модели макро-данных для Layer 3."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class YfinanceQuote(BaseModel):
    """Котировка из yfinance (Yahoo Finance — бесплатно).

    Все цены ``Decimal`` чтобы не терять precision при последующей сериализации.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    symbol: str = Field(min_length=1)
    timestamp_ms: int = Field(gt=0)
    last: Decimal
    change_pct_24h: Decimal | None = None
    volume_24h: Decimal | None = None


class MacroSnapshot(BaseModel):
    """Снапшот макро-картины для Macro Analyst Layer 3.

    Все поля Optional — какие-то источники могут быть down.
    Macro Analyst сам обрабатывает None кейсы.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    timestamp_ms: int = Field(gt=0)

    # Currency / vol indices
    dxy: Decimal | None = Field(default=None, description="DXY (US Dollar Index)")
    dxy_change_24h_pct: Decimal | None = None
    vix: Decimal | None = Field(default=None, description="VIX (S&P volatility)")
    vix_change_24h_pct: Decimal | None = None

    # Equities
    spx: Decimal | None = Field(default=None, description="S&P 500 spot/futures")
    ndx: Decimal | None = Field(default=None, description="NASDAQ-100 spot/futures")

    # Commodities
    gold: Decimal | None = Field(default=None, description="Gold (XAU/USD)")
    oil: Decimal | None = Field(default=None, description="Crude oil (WTI)")

    # Rates
    yield_10y: Decimal | None = Field(default=None, description="10-year Treasury yield (%)")

    # Crypto sector context (BTC dominance)
    btc_dominance_pct: Decimal | None = None

    # Free-form notes from адаптеров (e.g. "yfinance API down")
    warnings: tuple[str, ...] = ()
