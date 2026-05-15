"""Технические индикаторы. Чистые функции на Decimal — никаких float.

Все функции принимают ``Sequence[Kline]`` или ``Sequence[Decimal]`` и
возвращают одно ``Decimal``. Без побочных эффектов, без state.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from adapters.bingx.models import Kline


def sma(values: Sequence[Decimal], period: int) -> Decimal:
    """Простая скользящая средняя по последним ``period`` значениям.

    Если values меньше period — берёт всё что есть. Если 0 значений —
    `ValueError`.
    """
    if period <= 0:
        raise ValueError(f"period must be > 0, got {period}")
    if not values:
        raise ValueError("sma: empty values")
    window = values[-period:]
    return sum(window, Decimal("0")) / Decimal(len(window))


def ema(values: Sequence[Decimal], period: int) -> Decimal:
    """Экспоненциальная скользящая средняя.

    Стандартная формула: ``alpha = 2 / (period + 1)``. Первое значение
    инициализируется первым элементом values. Дальше:
    ``ema_i = alpha × value_i + (1 − alpha) × ema_{i−1}``.
    """
    if period <= 0:
        raise ValueError(f"period must be > 0, got {period}")
    if not values:
        raise ValueError("ema: empty values")
    alpha = Decimal("2") / Decimal(period + 1)
    one_minus_alpha = Decimal("1") - alpha
    current = values[0]
    for v in values[1:]:
        current = alpha * v + one_minus_alpha * current
    return current


def donchian_channel(candles: Sequence[Kline], period: int) -> tuple[Decimal, Decimal]:
    """``(upper, lower)`` за последние ``period`` свечей.

    Стратегия обычно сравнивает текущий close с этим каналом, передавая
    history БЕЗ текущей свечи (чтобы не сравнивать сам с собой).
    """
    if period <= 0:
        raise ValueError(f"period must be > 0, got {period}")
    if not candles:
        raise ValueError("donchian: empty candles")
    window = candles[-period:]
    upper = max(c.high for c in window)
    lower = min(c.low for c in window)
    return upper, lower


def true_range(candle: Kline, prev_close: Decimal | None) -> Decimal:
    """True Range одной свечи. Если нет prev_close — TR = high − low."""
    base = candle.high - candle.low
    if prev_close is None:
        return base
    return max(
        base,
        abs(candle.high - prev_close),
        abs(candle.low - prev_close),
    )


def atr(candles: Sequence[Kline], period: int) -> Decimal:
    """Wilder ATR.

    Первое значение = SMA(TR, period). Дальше: ``atr_i = (atr_{i-1} ×
    (period − 1) + TR_i) / period``. Это Wilder smoothing — стандарт для
    ATR (не путать с EMA).

    Минимум свечей: ``period + 1`` (одна для prev_close).
    """
    if period <= 0:
        raise ValueError(f"period must be > 0, got {period}")
    if len(candles) < period + 1:
        raise ValueError(f"atr: need at least {period + 1} candles, got {len(candles)}")

    # Считаем TR для каждой свечи начиная с 1-й (нужен prev_close).
    trs: list[Decimal] = []
    for i in range(1, len(candles)):
        trs.append(true_range(candles[i], candles[i - 1].close))

    # Wilder: первое значение = SMA первых `period` TR.
    initial = sum(trs[:period], Decimal("0")) / Decimal(period)
    current = initial
    period_dec = Decimal(period)
    one_minus_one_over_period = (period_dec - 1) / period_dec
    one_over_period = Decimal("1") / period_dec
    for tr in trs[period:]:
        current = current * one_minus_one_over_period + tr * one_over_period
    return current


def percentile_rank(values: Sequence[Decimal], value: Decimal) -> Decimal:
    """Доля values, которые ≤ value (0..1).

    Полезно для ATR-percentile фильтра: «ATR сейчас в верхней половине
    распределения за последние N свечей».
    """
    if not values:
        raise ValueError("percentile_rank: empty values")
    leq = sum(1 for v in values if v <= value)
    return Decimal(leq) / Decimal(len(values))
