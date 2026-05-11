"""Unit-тесты ``core.signals.session``."""

from __future__ import annotations

from core.signals import is_in_window, utc_day_of_epoch, utc_hour_of_day


def test_utc_hour_of_day_midnight() -> None:
    # 2024-01-01 00:00:00 UTC = 1704067200000 ms
    assert utc_hour_of_day(1704067200000) == 0


def test_utc_hour_of_day_noon() -> None:
    assert utc_hour_of_day(1704067200000 + 12 * 3600000) == 12


def test_utc_hour_of_day_almost_midnight() -> None:
    assert utc_hour_of_day(1704067200000 + 23 * 3600000) == 23


def test_utc_day_of_epoch_unique_per_day() -> None:
    day1 = utc_day_of_epoch(1704067200000)
    day2 = utc_day_of_epoch(1704067200000 + 86_400_000)
    assert day2 == day1 + 1


def test_is_in_window_open_close() -> None:
    base = 1704067200000  # midnight
    assert is_in_window(base, 0, 13) is True
    assert is_in_window(base + 12 * 3600000, 0, 13) is True
    # 13:00 — исключающая граница
    assert is_in_window(base + 13 * 3600000, 0, 13) is False
    assert is_in_window(base + 15 * 3600000, 0, 13) is False


def test_is_in_window_overnight_wraps_correctly() -> None:
    base = 1704067200000  # midnight
    # окно 22-06 UTC (overnight)
    assert is_in_window(base + 23 * 3600000, 22, 6) is True
    assert is_in_window(base + 3 * 3600000, 22, 6) is True
    assert is_in_window(base + 12 * 3600000, 22, 6) is False
