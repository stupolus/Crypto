"""Типизированные модели ответов Bybit V5 (только public market-data)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class BybitKline(_Strict):
    """V5 /market/kline row: [startTime, open, high, low, close, volume, turnover]."""

    start_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    turnover: Decimal


class BybitOISample(_Strict):
    """V5 /market/open-interest: {timestamp, openInterest}."""

    timestamp_ms: int
    open_interest: Decimal


class BybitFundingRate(_Strict):
    """V5 /market/funding/history: {symbol, fundingRate, fundingRateTimestamp}."""

    symbol: str
    funding_rate: Decimal
    funding_rate_timestamp_ms: int
