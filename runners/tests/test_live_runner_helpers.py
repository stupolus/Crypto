"""Unit-тесты helpers ``runners.live_runner``."""

from __future__ import annotations

from decimal import Decimal

import pytest

from runners.live_runner import (
    _build_kline_from_ws,
    _extract_candle_dict,
    _interval_to_ms,
    _KlineCloseDetector,
)


def _ws_msg(close_T: int, **fields: str) -> dict:
    """Хелпер: WS-сообщение BingX в реальном формате (без `x`/`t`)."""
    candle = {"o": "100", "h": "110", "l": "90", "c": "105", "v": "10"}
    candle.update(fields)
    candle["T"] = close_T
    return {"code": 0, "dataType": "BTC-USDT@kline_15m", "s": "BTC-USDT", "data": [candle]}


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


class TestKlineCloseDetector:
    """Покрываем баг §7 п.38: close detection через смену T."""

    def test_first_message_never_emits(self) -> None:
        """Первое сообщение — нет previous T → ничего не эмитим."""
        d = _KlineCloseDetector(interval_ms=900_000)
        assert d.feed(_ws_msg(close_T=1_700_000_900_000)) is None

    def test_same_T_no_emit(self) -> None:
        """N сообщений с тем же T — свеча открыта, close не эмитим."""
        d = _KlineCloseDetector(interval_ms=900_000)
        d.feed(_ws_msg(close_T=1_700_000_900_000, c="100"))
        assert d.feed(_ws_msg(close_T=1_700_000_900_000, c="101")) is None
        assert d.feed(_ws_msg(close_T=1_700_000_900_000, c="102")) is None

    def test_T_change_emits_previous_snapshot(self) -> None:
        """Смена T → эмитим последний snapshot предыдущей свечи."""
        d = _KlineCloseDetector(interval_ms=900_000)
        d.feed(_ws_msg(close_T=1_700_000_900_000, c="100"))
        d.feed(_ws_msg(close_T=1_700_000_900_000, c="105"))  # последний snapshot
        # Следующая свеча открылась.
        closed = d.feed(_ws_msg(close_T=1_700_001_800_000, c="107"))
        assert closed is not None
        # open_time = previous_T - interval_ms.
        assert closed.open_time_ms == 1_700_000_900_000 - 900_000
        # close взят из последнего snapshot предыдущей свечи (c="105").
        assert closed.close == Decimal("105")

    def test_multiple_closes_in_sequence(self) -> None:
        """Несколько закрытий подряд — каждое корректно отдаётся."""
        d = _KlineCloseDetector(interval_ms=60_000)
        d.feed(_ws_msg(close_T=1_700_000_060_000, c="100"))
        c1 = d.feed(_ws_msg(close_T=1_700_000_120_000, c="101"))
        c2 = d.feed(_ws_msg(close_T=1_700_000_180_000, c="102"))
        c3 = d.feed(_ws_msg(close_T=1_700_000_240_000, c="103"))
        assert c1 is not None and c1.close == Decimal("100")
        assert c2 is not None and c2.close == Decimal("101")
        assert c3 is not None and c3.close == Decimal("102")

    def test_invalid_payload_ignored(self) -> None:
        """Невалидные сообщения не ломают state."""
        d = _KlineCloseDetector(interval_ms=900_000)
        d.feed(_ws_msg(close_T=1_700_000_900_000))
        assert d.feed({}) is None
        assert d.feed({"data": []}) is None
        assert d.feed({"data": [{"o": "1"}]}) is None  # без T
        # State не сломан: смена T продолжает работать.
        closed = d.feed(_ws_msg(close_T=1_700_001_800_000))
        assert closed is not None


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
