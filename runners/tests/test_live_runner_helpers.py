"""Unit-тесты helpers ``runners.live_runner``."""

from __future__ import annotations

from decimal import Decimal

import pytest

from runners.live_runner import (
    _build_kline_from_ws,
    _extract_candle_dict,
    _interval_to_ms,
)


def test_interval_to_ms_known() -> None:
    assert _interval_to_ms("1m") == 60_000
    assert _interval_to_ms("15m") == 900_000
    assert _interval_to_ms("1h") == 3_600_000
    assert _interval_to_ms("4h") == 14_400_000
    assert _interval_to_ms("1d") == 86_400_000


def test_interval_to_ms_unknown_raises() -> None:
    with pytest.raises(SystemExit):
        _interval_to_ms("2.5m")


def test_extract_candle_dict_returns_first_valid_entry() -> None:
    """Реальный формат BingX WS (квирк §7 п.38): без `x` / `t`, только `T`."""
    payload = {
        "code": 0,
        "dataType": "BTC-USDT@kline_15m",
        "s": "BTC-USDT",
        "data": [
            {
                "c": "60100",
                "o": "60000",
                "h": "60200",
                "l": "59900",
                "v": "100",
                "T": 1_700_000_900_000,
            }
        ],
    }
    candle = _extract_candle_dict(payload)
    assert candle is not None
    assert candle["c"] == "60100"
    assert candle["T"] == 1_700_000_900_000


def test_extract_candle_dict_empty_or_invalid() -> None:
    assert _extract_candle_dict({}) is None
    assert _extract_candle_dict({"data": []}) is None
    assert _extract_candle_dict({"data": "not-a-list"}) is None
    # Без T — невалидно для нашей логики.
    assert _extract_candle_dict({"data": [{"o": "1"}]}) is None


def test_build_kline_from_ws() -> None:
    candle_dict = {
        "c": "60100",
        "o": "60000",
        "h": "60200",
        "l": "59900",
        "v": "100",
        "T": 1_700_000_900_000,
    }
    kline = _build_kline_from_ws(candle_dict, open_time_ms=1_700_000_000_000)
    assert kline.open_time_ms == 1_700_000_000_000
    assert kline.open == Decimal("60000")
    assert kline.close == Decimal("60100")
    assert kline.high == Decimal("60200")
    assert kline.low == Decimal("59900")
