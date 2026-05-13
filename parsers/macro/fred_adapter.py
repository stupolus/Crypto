"""FRED adapter — Fed Funds Rate, CPI, unemployment через FRED API.

Источник: FRED (Federal Reserve Economic Data) — официальный API
Federal Reserve Bank of St. Louis. Бесплатно, регистрация ~1 минута:
https://fred.stlouisfed.org/docs/api/api_key.html

Используется для построения MacroSnapshot — дополняет yfinance
макро-серии которых нет в Yahoo:
- Effective Federal Funds Rate (DFF / FEDFUNDS)
- CPI urban consumers (CPIAUCSL)
- Unemployment rate (UNRATE)
- 10Y minus 2Y Treasury spread (T10Y2Y) — рецессионный индикатор

Production fetcher выполняет httpx GET на api.stlouisfed.org;
тесты используют MockFREDFetcher через FREDFetcher Protocol.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Protocol

logger = logging.getLogger(__name__)

# Mapping: внутреннее имя → FRED series ID
_FRED_SERIES: dict[str, str] = {
    "fed_funds_rate": "DFF",  # daily, % per annum
    "cpi_urban": "CPIAUCSL",  # monthly, index 1982-1984=100
    "unemployment_rate": "UNRATE",  # monthly, %
    "yield_spread_10y_2y": "T10Y2Y",  # daily, %
}


class FREDFetcher(Protocol):
    """Контракт реального FRED API client'а.

    fetch_latest(series_ids) → dict[series_id, Decimal] последних observations.
    """

    def fetch_latest(self, series_ids: list[str]) -> dict[str, Decimal]: ...


class FREDSnapshot:
    """Snapshot ключевых FRED индикаторов на момент вызова.

    Замечание: тут не используем pydantic — Decimal-словарь достаточен.
    Если нужно — можно расширить до полноценной pydantic-модели позже.
    """

    def __init__(
        self,
        fed_funds_rate: Decimal | None = None,
        cpi_urban: Decimal | None = None,
        unemployment_rate: Decimal | None = None,
        yield_spread_10y_2y: Decimal | None = None,
        warnings: tuple[str, ...] = (),
    ) -> None:
        self.fed_funds_rate = fed_funds_rate
        self.cpi_urban = cpi_urban
        self.unemployment_rate = unemployment_rate
        self.yield_spread_10y_2y = yield_spread_10y_2y
        self.warnings = warnings

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FREDSnapshot):
            return NotImplemented
        return (
            self.fed_funds_rate == other.fed_funds_rate
            and self.cpi_urban == other.cpi_urban
            and self.unemployment_rate == other.unemployment_rate
            and self.yield_spread_10y_2y == other.yield_spread_10y_2y
            and self.warnings == other.warnings
        )

    def __repr__(self) -> str:
        return (
            f"FREDSnapshot(fed_funds={self.fed_funds_rate}, "
            f"cpi={self.cpi_urban}, unemp={self.unemployment_rate}, "
            f"yield_spread={self.yield_spread_10y_2y}, "
            f"warnings={self.warnings})"
        )


class FREDAdapter:
    """Адаптер ключевых FRED индикаторов.

    DI fetcher → тесты подменяют без реальных API-вызовов.

    Defensive: при ошибке fetch — пустой snapshot с warning, не валит
    остальной поток (Macro Analyst может работать частично).
    """

    def __init__(self, fetcher: FREDFetcher) -> None:
        self._fetcher = fetcher

    def snapshot(self) -> FREDSnapshot:
        warnings: list[str] = []
        series_ids = list(_FRED_SERIES.values())
        try:
            observations = self._fetcher.fetch_latest(series_ids)
        except Exception as e:
            logger.error("FRED fetch failed: %s", e)
            return FREDSnapshot(warnings=(f"FRED fetch failed: {e}",))

        result_values: dict[str, Decimal | None] = {}
        for internal_name, fred_id in _FRED_SERIES.items():
            value = observations.get(fred_id)
            if value is None:
                warnings.append(f"FRED: {fred_id} not in response")
                result_values[internal_name] = None
            else:
                result_values[internal_name] = value

        return FREDSnapshot(
            fed_funds_rate=result_values.get("fed_funds_rate"),
            cpi_urban=result_values.get("cpi_urban"),
            unemployment_rate=result_values.get("unemployment_rate"),
            yield_spread_10y_2y=result_values.get("yield_spread_10y_2y"),
            warnings=tuple(warnings),
        )
