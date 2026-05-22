"""Чистые функции-индикаторы на Decimal.

Без состояния, без сети, без lookahead: каждая функция считает по переданному
срезу истории. Стратегии и бэктестер вызывают их на `history[:i+1]` — будущее
функции не видят.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from exchanges.models import OHLCV

_TWO = Decimal(2)
_HUNDRED = Decimal(100)


def ema(values: Sequence[Decimal], period: int) -> list[Decimal]:
    """Экспоненциальная скользящая. Первое значение — SMA первых `period`.

    Возвращает список длиной len(values) - period + 1 (по одному EMA на каждую
    позицию начиная с period-й). Пусто, если данных меньше period.
    """
    if period <= 0:
        raise ValueError("period должен быть > 0")
    if len(values) < period:
        return []
    k = _TWO / Decimal(period + 1)
    seed = sum(values[:period], Decimal(0)) / Decimal(period)
    out = [seed]
    prev = seed
    for v in values[period:]:
        prev = (v - prev) * k + prev
        out.append(prev)
    return out


def atr(candles: Sequence[OHLCV], period: int) -> list[Decimal]:
    """Average True Range (по Уайлдеру: SMA первого TR-окна, далее сглаживание).

    Возвращает по одному ATR на каждую свечу начиная с (period)-й true range.
    Пусто, если свечей меньше period + 1.
    """
    if period <= 0:
        raise ValueError("period должен быть > 0")
    if len(candles) < period + 1:
        return []
    trs: list[Decimal] = []
    for i in range(1, len(candles)):
        c = candles[i]
        prev_close = candles[i - 1].close
        tr = max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
        trs.append(tr)
    first = sum(trs[:period], Decimal(0)) / Decimal(period)
    out = [first]
    prev = first
    for tr in trs[period:]:
        prev = (prev * Decimal(period - 1) + tr) / Decimal(period)
        out.append(prev)
    return out


def donchian(candles: Sequence[OHLCV], period: int) -> tuple[Decimal, Decimal] | None:
    """Канал Дончиана за последние `period` свечей: (верх, низ). None если мало данных.

    Не включает текущую свечу-кандидат на пробой — берёт последние `period`
    ЗАКРЫТЫХ свечей, переданных в срезе (ответственность вызывающего — не
    передавать незакрытую свечу).
    """
    if period <= 0:
        raise ValueError("period должен быть > 0")
    if len(candles) < period:
        return None
    window = candles[-period:]
    upper = max(c.high for c in window)
    lower = min(c.low for c in window)
    return upper, lower


def rsi(values: Sequence[Decimal], period: int) -> list[Decimal]:
    """RSI по Уайлдеру. Возвращает по одному значению начиная с (period)-го изменения.

    При нулевых средних потерях RSI = 100. Пусто, если данных меньше period + 1.
    """
    if period <= 0:
        raise ValueError("period должен быть > 0")
    if len(values) < period + 1:
        return []
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(delta if delta > 0 else Decimal(0))
        losses.append(-delta if delta < 0 else Decimal(0))

    avg_gain = sum(gains[:period], Decimal(0)) / Decimal(period)
    avg_loss = sum(losses[:period], Decimal(0)) / Decimal(period)
    out = [_rsi_value(avg_gain, avg_loss)]
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * Decimal(period - 1) + gains[i]) / Decimal(period)
        avg_loss = (avg_loss * Decimal(period - 1) + losses[i]) / Decimal(period)
        out.append(_rsi_value(avg_gain, avg_loss))
    return out


def _rsi_value(avg_gain: Decimal, avg_loss: Decimal) -> Decimal:
    if avg_loss == 0:
        return _HUNDRED
    rs = avg_gain / avg_loss
    return _HUNDRED - (_HUNDRED / (Decimal(1) + rs))


def vwap(candles: Sequence[OHLCV]) -> Decimal | None:
    """Volume-weighted average price по переданному окну (typical price × volume).

    Сброс по сессии — ответственность вызывающего (передаёт нужный срез).
    None если суммарный объём ноль или окно пусто.
    """
    if not candles:
        return None
    pv = Decimal(0)
    vol = Decimal(0)
    for c in candles:
        typical = (c.high + c.low + c.close) / Decimal(3)
        pv += typical * c.volume
        vol += c.volume
    if vol == 0:
        return None
    return pv / vol
