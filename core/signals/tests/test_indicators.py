"""Unit-тесты ``core.signals.indicators``."""

from __future__ import annotations

from decimal import Decimal

import pytest

from adapters.bingx.models import Kline
from core.signals import (
    atr,
    donchian_channel,
    ema,
    percentile_rank,
    sma,
    true_range,
)


def _kline(open_: str, high: str, low: str, close: str, t: int = 0) -> Kline:
    return Kline.model_validate(
        {
            "time": t,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": "100",
        }
    )


def test_sma_basic() -> None:
    values = [Decimal(v) for v in ("1", "2", "3", "4", "5")]
    assert sma(values, 5) == Decimal("3")
    assert sma(values, 3) == Decimal("4")  # последние 3: 3+4+5 = 12/3 = 4


def test_sma_short_window_uses_all_available() -> None:
    values = [Decimal("10"), Decimal("20")]
    assert sma(values, 5) == Decimal("15")


def test_sma_empty_raises() -> None:
    with pytest.raises(ValueError):
        sma([], 3)


def test_ema_converges_to_constant() -> None:
    """На константном ряде EMA = константа после warmup."""
    values = [Decimal("100")] * 50
    assert ema(values, 21) == Decimal("100")


def test_ema_responds_to_step() -> None:
    """EMA реагирует, но плавнее SMA."""
    values = [Decimal("100")] * 20 + [Decimal("200")] * 10
    e = ema(values, 10)
    # После 10 свечей на уровне 200, EMA должен быть между 100 и 200,
    # ближе к 200.
    assert Decimal("150") < e < Decimal("200")


def test_donchian_channel() -> None:
    candles = [
        _kline("100", "110", "95", "108", 0),
        _kline("108", "115", "100", "112", 60),
        _kline("112", "118", "105", "116", 120),
    ]
    upper, lower = donchian_channel(candles, period=3)
    assert upper == Decimal("118")
    assert lower == Decimal("95")


def test_true_range_first_candle_no_prev_close() -> None:
    c = _kline("100", "110", "90", "105")
    assert true_range(c, None) == Decimal("20")


def test_true_range_uses_max_of_three() -> None:
    c = _kline("100", "108", "95", "105")
    prev_close = Decimal("80")
    # high-low = 13; |high-prev| = 28; |low-prev| = 15 → 28
    assert true_range(c, prev_close) == Decimal("28")


def test_atr_wilder_basic() -> None:
    """ATR на стабильном диапазоне (5) должен быть ~5."""
    candles = []
    for i in range(20):
        candles.append(_kline("100", "102", "97", "100", i * 60))
    # high-low = 5 для каждой; prev_close=100; TR = max(5, |102-100|, |97-100|) = 5
    result = atr(candles, period=14)
    assert result == Decimal("5")


def test_atr_requires_minimum_history() -> None:
    candles = [_kline("100", "102", "98", "100", i) for i in range(5)]
    with pytest.raises(ValueError):
        atr(candles, period=14)


def test_percentile_rank() -> None:
    values = [Decimal(str(v)) for v in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)]
    # 5 ≤ 5/10 = 50%
    assert percentile_rank(values, Decimal("5")) == Decimal("0.5")
    # 10 ≤ 10/10 = 100%
    assert percentile_rank(values, Decimal("10")) == Decimal("1")
    # 0 ≤ 0/10
    assert percentile_rank(values, Decimal("0")) == Decimal("0")
