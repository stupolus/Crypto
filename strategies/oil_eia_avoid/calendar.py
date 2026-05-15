"""EIA blackout news-calendar для OilEiaAvoid.

EIA Petroleum Status Report выходит каждую среду в 10:30 EST → 14:30 UTC
(зимой) / 15:30 UTC (DST). Релиз вызывает мгновенный 1-2% move на WTI/
Brent — слишком волатильно для breakout-стратегии.

Решение: blackout-окно ±30 мин вокруг релиза. Для упрощения в MVP — широкое
окно Wed 14:00-16:00 UTC, покрывающее оба DST-варианта.

Источник расписания: EIA Weekly Petroleum Status (eia.gov).
"""

from __future__ import annotations

from core.signals import NewsCalendar, WeeklyEventCalendar


def build_eia_news_calendar() -> NewsCalendar:
    """Wed 14:00-16:00 UTC pause-окно (покрывает DST/non-DST EIA release)."""
    return WeeklyEventCalendar(
        weekday=2,  # Wednesday
        start_hour=14,
        start_minute=0,
        end_hour=16,
        end_minute=0,
    )
