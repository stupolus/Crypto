"""Тесты индикаторов: сверка с ручным расчётом."""

from __future__ import annotations

from decimal import Decimal

import pytest

from exchanges.models import OHLCV
from indicators.core import atr, donchian, ema, rsi, vwap


def _candle(high: str, low: str, close: str, volume: str = "1", ts: int = 0) -> OHLCV:
    return OHLCV(
        timestamp=ts,
        open=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
    )


def test_ema_seed_is_sma() -> None:
    vals = [Decimal(x) for x in (1, 2, 3, 4, 5)]
    out = ema(vals, 3)
    # первое значение — SMA(1,2,3) = 2
    assert out[0] == Decimal(2)
    assert len(out) == 3


def test_ema_known_progression() -> None:
    vals = [Decimal(x) for x in (1, 2, 3, 4, 5)]
    out = ema(vals, 3)
    k = Decimal(2) / Decimal(4)  # 0.5
    expected1 = (Decimal(4) - Decimal(2)) * k + Decimal(2)  # 3
    assert out[1] == expected1


def test_ema_too_short() -> None:
    assert ema([Decimal(1), Decimal(2)], 3) == []


def test_ema_invalid_period() -> None:
    with pytest.raises(ValueError):
        ema([Decimal(1)], 0)


def test_atr_simple() -> None:
    # все свечи с range 2, prev_close внутри — TR = 2 каждая
    candles = [_candle("12", "10", "11", ts=i) for i in range(5)]
    out = atr(candles, 3)
    assert out[0] == Decimal(2)
    assert all(v == Decimal(2) for v in out)


def test_atr_too_short() -> None:
    candles = [_candle("12", "10", "11", ts=i) for i in range(3)]
    assert atr(candles, 3) == []


def test_donchian() -> None:
    candles = [
        _candle("10", "5", "8", ts=0),
        _candle("12", "6", "9", ts=1),
        _candle("11", "4", "7", ts=2),
    ]
    result = donchian(candles, 3)
    assert result == (Decimal(12), Decimal(4))


def test_donchian_too_short() -> None:
    assert donchian([_candle("10", "5", "8")], 3) is None


def test_rsi_all_gains_is_100() -> None:
    vals = [Decimal(x) for x in (1, 2, 3, 4, 5, 6)]
    out = rsi(vals, 3)
    assert out[0] == Decimal(100)


def test_rsi_mixed_in_range() -> None:
    vals = [Decimal(x) for x in (10, 11, 10, 12, 11, 13)]
    out = rsi(vals, 3)
    assert all(Decimal(0) <= v <= Decimal(100) for v in out)


def test_rsi_too_short() -> None:
    assert rsi([Decimal(1), Decimal(2)], 3) == []


def test_vwap_weighted() -> None:
    candles = [
        _candle("10", "10", "10", volume="1"),  # typical 10
        _candle("20", "20", "20", volume="3"),  # typical 20
    ]
    # (10*1 + 20*3) / (1+3) = 70/4 = 17.5
    assert vwap(candles) == Decimal("17.5")


def test_vwap_zero_volume_none() -> None:
    assert vwap([_candle("10", "10", "10", volume="0")]) is None


def test_vwap_empty_none() -> None:
    assert vwap([]) is None
