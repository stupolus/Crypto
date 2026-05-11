"""Unit-тесты helpers ``runners.live_runner``."""

from __future__ import annotations

from decimal import Decimal

import pytest

from runners.live_runner import _decode_kline_message, _interval_to_ms


def test_interval_to_ms_known() -> None:
    assert _interval_to_ms("1m") == 60_000
    assert _interval_to_ms("15m") == 900_000
    assert _interval_to_ms("1h") == 3_600_000
    assert _interval_to_ms("4h") == 14_400_000
    assert _interval_to_ms("1d") == 86_400_000


def test_interval_to_ms_unknown_raises() -> None:
    with pytest.raises(SystemExit):
        _interval_to_ms("2.5m")


def test_decode_kline_message_returns_none_for_open_candle() -> None:
    """Если ``x: False`` (свеча не закрылась) — None."""
    payload = {
        "data": [
            {
                "t": 1_700_000_000_000,
                "T": 1_700_000_900_000,
                "o": "60000",
                "c": "60100",
                "h": "60200",
                "l": "59900",
                "v": "100",
                "x": False,
            }
        ]
    }
    assert _decode_kline_message(payload) is None


def test_decode_kline_message_returns_kline_for_closed() -> None:
    payload = {
        "data": [
            {
                "t": 1_700_000_000_000,
                "T": 1_700_000_900_000,
                "o": "60000",
                "c": "60100",
                "h": "60200",
                "l": "59900",
                "v": "100",
                "x": True,
            }
        ]
    }
    kline = _decode_kline_message(payload)
    assert kline is not None
    assert kline.open_time_ms == 1_700_000_000_000
    assert kline.open == Decimal("60000")
    assert kline.close == Decimal("60100")
    assert kline.high == Decimal("60200")
    assert kline.low == Decimal("59900")


def test_decode_kline_message_empty_payload() -> None:
    assert _decode_kline_message({}) is None
    assert _decode_kline_message({"data": []}) is None
    assert _decode_kline_message({"data": "not-a-list"}) is None
