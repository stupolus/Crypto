"""Тесты на WeeklyEventCalendar и CompositeNewsCalendar."""

from __future__ import annotations

from datetime import UTC, datetime

from core.signals import (
    CompositeNewsCalendar,
    StaticNewsCalendar,
    WeeklyEventCalendar,
)


def _ms(year: int, month: int, day: int, hour: int, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp() * 1000)


def test_weekly_event_calendar_pauses_on_matching_day_and_window() -> None:
    """EIA Wed 14:00-15:30 UTC."""
    cal = WeeklyEventCalendar(
        weekday=2,  # Wednesday
        start_hour=14,
        start_minute=0,
        end_hour=15,
        end_minute=30,
    )
    # Wed 2026-05-13 (weekday=2 в этой неделе)
    assert cal.is_paused(_ms(2026, 5, 13, 14, 15)) is True  # внутри окна
    assert cal.is_paused(_ms(2026, 5, 13, 14, 0)) is True  # на границе start
    assert cal.is_paused(_ms(2026, 5, 13, 15, 30)) is True  # на границе end
    assert cal.is_paused(_ms(2026, 5, 13, 13, 59)) is False  # перед окном
    assert cal.is_paused(_ms(2026, 5, 13, 15, 31)) is False  # после окна
    # Tue 2026-05-12 — не Wed
    assert cal.is_paused(_ms(2026, 5, 12, 14, 15)) is False


def test_weekly_event_calendar_single_minute_window() -> None:
    """end_hour=None → single-minute pause (start_hour:start_minute only)."""
    cal = WeeklyEventCalendar(weekday=4, start_hour=20, start_minute=0)
    # Fri 2026-05-15 20:00 (NY close ~16:00 EST на DST)
    assert cal.is_paused(_ms(2026, 5, 15, 20, 0)) is True
    assert cal.is_paused(_ms(2026, 5, 15, 19, 59)) is False
    assert cal.is_paused(_ms(2026, 5, 15, 20, 1)) is False


def test_weekly_event_calendar_invalid_weekday() -> None:
    import pytest

    with pytest.raises(ValueError):
        WeeklyEventCalendar(weekday=7, start_hour=14)


def test_composite_news_calendar_or_semantics() -> None:
    """Любой child paused → composite paused."""
    eia = WeeklyEventCalendar(weekday=2, start_hour=14, end_hour=15, end_minute=30)
    fomc = StaticNewsCalendar(pause_windows=[(_ms(2026, 5, 15, 18, 0), _ms(2026, 5, 15, 19, 0))])
    composite = CompositeNewsCalendar([eia, fomc])

    # Wed во время EIA
    assert composite.is_paused(_ms(2026, 5, 13, 14, 30)) is True
    # Fri во время FOMC
    assert composite.is_paused(_ms(2026, 5, 15, 18, 30)) is True
    # Tue вне всех окон
    assert composite.is_paused(_ms(2026, 5, 12, 12, 0)) is False
