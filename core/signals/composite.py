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

    def get_funding_rate(
        self, symbol: str, timestamp_ms: int
    ) -> Decimal | None: ...


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

    def get_funding_rate(
        self, symbol: str, timestamp_ms: int
    ) -> Decimal | None:
        return self._rates.get(symbol)


class StaticNewsCalendar:
    """Статичный календарь pause-окон.

    ``pause_windows`` — список ``(start_ms, end_ms)``. Если ``ts`` попадает
    в любое окно — paused.
    """

    def __init__(self, pause_windows: Iterable[tuple[int, int]] | None = None) -> None:
        self._windows = tuple(pause_windows or ())

    def is_paused(self, timestamp_ms: int) -> bool:
        return any(
            start <= timestamp_ms <= end for start, end in self._windows
        )


class SetBlacklist:
    """Set-based blacklist. По умолчанию пуст."""

    def __init__(self, symbols: Iterable[str] | None = None) -> None:
        self._symbols = set(symbols or ())

    def contains(self, symbol: str) -> bool:
        return symbol in self._symbols


__all__ = [
    "Blacklist",
    "FundingProvider",
    "NewsCalendar",
    "SetBlacklist",
    "StaticFundingProvider",
    "StaticNewsCalendar",
]
