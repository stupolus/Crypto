"""Session / time-of-day helpers.

Используются стратегиями с time-фильтром (например, US session open
breakout). Все timestamp'ы — миллисекунды UTC epoch.
"""

from __future__ import annotations

_MS_PER_HOUR = 3_600_000
_MS_PER_DAY = 86_400_000


def utc_hour_of_day(timestamp_ms: int) -> int:
    """Час дня UTC (0..23) для данного timestamp.

    Простая арифметика по epoch — никаких datetime/zoneinfo, чтобы избежать
    overhead при тысячах вызовов в backtest.
    """
    return (timestamp_ms // _MS_PER_HOUR) % 24


def utc_day_of_epoch(timestamp_ms: int) -> int:
    """Номер дня с UTC epoch. Уникален для каждого календарного дня UTC."""
    return timestamp_ms // _MS_PER_DAY


def is_in_window(
    timestamp_ms: int, start_hour_utc: int, end_hour_utc: int
) -> bool:
    """Проверка, попадает ли ts в окно ``[start_hour, end_hour)`` UTC.

    Окно полуоткрытое: start включается, end исключается. ``end < start``
    означает overnight окно (например 22-06 UTC).
    """
    h = utc_hour_of_day(timestamp_ms)
    if start_hour_utc < end_hour_utc:
        return start_hour_utc <= h < end_hour_utc
    # Overnight (wrap-around).
    return h >= start_hour_utc or h < end_hour_utc
