"""Earnings blackout calendar для StockEarningsAvoid.

Earnings releases для TSLA / NVDA вызывают gap'ы 5-15% после-hours.
Решение: blackout ±2 рабочих дня вокруг даты earnings.

В MVP — hardcoded список ближайших earnings дат. На live — заменим
на провайдер (Finnhub / Polygon / Alpha Vantage).

Источник дат: investor.com / company IR pages.

Расширение: ``upcoming_earnings_dates`` принимается параметром →
можно дойти до полноценного provider'а позже без перелопачивания
strategy кода.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.signals import NewsCalendar, StaticNewsCalendar

# Ближайшие earnings releases (UTC даты после-close). Обновлять
# вручную до того как сделаем provider.
# TSLA: после-close = ~20:00 UTC (16:00 EST на DST).
# NVDA: аналогично.
DEFAULT_UPCOMING_EARNINGS: dict[str, tuple[str, ...]] = {
    "TSLA-USDT": (
        # Q2 2026 results, expected late July
        "2026-07-23",
        # Q3 2026 results, expected late October
        "2026-10-22",
    ),
    "NVDA-USDT": (
        # Q1 FY2027 results, expected late May
        "2026-05-28",
        # Q2 FY2027, expected late August
        "2026-08-27",
    ),
}

# Blackout window: ±N календарных дней вокруг earnings date.
# 2 дня — pre-event uncertainty + post-event gap absorption.
BLACKOUT_DAYS = 2


def build_earnings_blackout_calendar(
    symbol: str,
    earnings_dates: tuple[str, ...] | None = None,
    blackout_days: int = BLACKOUT_DAYS,
) -> NewsCalendar:
    """StaticNewsCalendar с окнами ±blackout_days вокруг каждой даты.

    Args:
        symbol: тикер (для DEFAULT_UPCOMING_EARNINGS lookup)
        earnings_dates: явный override списка дат YYYY-MM-DD; если None,
            берётся из DEFAULT_UPCOMING_EARNINGS[symbol].
        blackout_days: размер blackout-окна в днях (default 2).
    """
    dates = earnings_dates or DEFAULT_UPCOMING_EARNINGS.get(symbol, ())
    windows: list[tuple[int, int]] = []
    delta = timedelta(days=blackout_days)
    for date_str in dates:
        # Полночь UTC даты earnings ± окно
        center = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        start = center - delta
        end = center + delta + timedelta(days=1)  # включая весь день +N
        windows.append(
            (
                int(start.timestamp() * 1000),
                int(end.timestamp() * 1000),
            )
        )
    return StaticNewsCalendar(pause_windows=windows)
