"""Pydantic-парсинг Kline и Ticker из реальных V5 payloads (формат из доков)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from adapters.bybit.models import Kline, Ticker


def test_kline_from_v5_row_basic() -> None:
    """V5 kline-строка → объект, все поля числовые."""
    row = [
        "1700000000000",  # start_ms
        "30000.5",  # open
        "30100.0",  # high
        "29900.0",  # low
        "30050.0",  # close
        "10.5",  # volume
        "315525.0",  # turnover
    ]
    k = Kline.from_v5_row(row)
    assert k.start_ms == 1700000000000
    assert k.open == Decimal("30000.5")
    assert k.high == Decimal("30100.0")
    assert k.low == Decimal("29900.0")
    assert k.close == Decimal("30050.0")
    assert k.volume == Decimal("10.5")
    assert k.turnover == Decimal("315525.0")


def test_kline_from_v5_row_wrong_length_raises() -> None:
    with pytest.raises(ValueError, match="must have 7 fields"):
        Kline.from_v5_row(["1", "2", "3"])


def test_ticker_from_v5_payload_with_alias() -> None:
    """Bybit отдаёт lastPrice/markPrice — pydantic alias подхватывает."""
    payload = {
        "symbol": "BTC-USDT",
        "lastPrice": "30050.5",
        "markPrice": "30048.0",
        "indexPrice": "30049.0",
        "openInterest": "1234.56",
        "fundingRate": "0.0001",
        "bid1Price": "30050.0",
        "ask1Price": "30051.0",
        "volume24h": "1000",
        "turnover24h": "30000000",
        # лишние поля для проверки extra=ignore:
        "prevPrice24h": "29000",
        "highPrice24h": "31000",
    }
    t = Ticker(**payload)
    assert t.symbol == "BTC-USDT"
    assert t.last_price == Decimal("30050.5")
    assert t.mark_price == Decimal("30048.0")
    assert t.index_price == Decimal("30049.0")
    assert t.open_interest == Decimal("1234.56")
    assert t.funding_rate == Decimal("0.0001")


def test_ticker_optional_fields_default_none() -> None:
    """OI/funding/etc. могут отсутствовать в payload — Optional → None."""
    payload = {
        "symbol": "BTC-USDT",
        "lastPrice": "1",
        "markPrice": "1",
        "indexPrice": "1",
    }
    t = Ticker(**payload)
    assert t.open_interest is None
    assert t.funding_rate is None
    assert t.bid1_price is None
