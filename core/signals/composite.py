"""Composite-state providers: funding, news, blacklist.

В live эти провайдеры обёртывают реальные источники (BingX
`/premiumIndex` для funding, Forex Factory для news). В backtest и
unit-тестах — статичные in-memory заглушки.

Стратегия зависит только от protocol'ов — реализация подключается
через DI на старте процесса (live) или в фикстуре (тест).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Protocol, runtime_checkable


@runtime_checkable
class FundingProvider(Protocol):
    """Источник текущего funding rate per symbol."""

    def get_funding_rate(self, symbol: str, timestamp_ms: int) -> Decimal | None: ...


@runtime_checkable
class NewsCalendar(Protocol):
    """High-impact news calendar."""

    def is_paused(self, timestamp_ms: int) -> bool: ...


@runtime_checkable
class Blacklist(Protocol):
    """Список символов, на которых не торгуем (manipulation pattern)."""

    def contains(self, symbol: str) -> bool: ...


# ── In-memory реализации для тестов / MVP ────────────────────────────────


class StaticFundingProvider:
    """Возвращает фиксированный funding per symbol. Не зависит от ts.

    Для backtest на исторических данных можно передать ``None`` для
    каждого символа — composite-фильтр пропустит сделки без проверки.
    """

    def __init__(self, rates: Mapping[str, Decimal | None] | None = None) -> None:
        self._rates = dict(rates) if rates else {}

    def get_funding_rate(self, symbol: str, timestamp_ms: int) -> Decimal | None:
        return self._rates.get(symbol)


class StaticNewsCalendar:
    """Статичный календарь pause-окон.

    ``pause_windows`` — список ``(start_ms, end_ms)``. Если ``ts`` попадает
    в любое окно — paused.
    """

    def __init__(self, pause_windows: Iterable[tuple[int, int]] | None = None) -> None:
        self._windows = tuple(pause_windows or ())

    def is_paused(self, timestamp_ms: int) -> bool:
        return any(start <= timestamp_ms <= end for start, end in self._windows)


class SetBlacklist:
    """Set-based blacklist. По умолчанию пуст."""

    def __init__(self, symbols: Iterable[str] | None = None) -> None:
        self._symbols = set(symbols or ())

    def contains(self, symbol: str) -> bool:
        return symbol in self._symbols


class WeeklyEventCalendar:
    """Recurring weekly pause-окно: каждый weekday X с time A до time B UTC.

    Применение — EIA Petroleum Status Report (Wed 14:30 UTC ±N мин),
    funding settlement, открытие US session, и т.п. Несколько окон
    можно собрать в один календарь через несколько экземпляров +
    composite-обёртку.

    Args:
        weekday: 0=Monday..6=Sunday (стандарт ``datetime.weekday``)
        start_hour: UTC hour, 0..23
        start_minute: UTC minute, 0..59
        end_hour: UTC hour, 0..23 (>= start_hour same-day)
        end_minute: UTC minute, 0..59
    """

    def __init__(
        self,
        *,
        weekday: int,
        start_hour: int,
        start_minute: int = 0,
        end_hour: int | None = None,
        end_minute: int = 0,
    ) -> None:
        if not 0 <= weekday <= 6:
            raise ValueError(f"weekday must be 0..6, got {weekday}")
        if not 0 <= start_hour <= 23:
            raise ValueError(f"start_hour must be 0..23, got {start_hour}")
        if end_hour is None:
            end_hour = start_hour
        self._weekday = weekday
        self._start_min_of_day = start_hour * 60 + start_minute
        self._end_min_of_day = end_hour * 60 + end_minute
        if self._end_min_of_day < self._start_min_of_day:
            raise ValueError("end must be >= start (same-day window only)")

    def is_paused(self, timestamp_ms: int) -> bool:
        # Импорт здесь чтобы не тянуть datetime в hot-path module-level.
        from datetime import UTC, datetime

        dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
        if dt.weekday() != self._weekday:
            return False
        mod = dt.hour * 60 + dt.minute
        return self._start_min_of_day <= mod <= self._end_min_of_day


class CompositeNewsCalendar:
    """Объединение нескольких NewsCalendar — paused если ЛЮБОЙ paused."""

    def __init__(self, calendars: Iterable[NewsCalendar]) -> None:
        self._calendars = tuple(calendars)

    def is_paused(self, timestamp_ms: int) -> bool:
        return any(c.is_paused(timestamp_ms) for c in self._calendars)


__all__ = [
    "Blacklist",
    "CompositeNewsCalendar",
    "FundingProvider",
    "NewsCalendar",
    "SetBlacklist",
    "StaticFundingProvider",
    "StaticNewsCalendar",
    "WeeklyEventCalendar",
]
