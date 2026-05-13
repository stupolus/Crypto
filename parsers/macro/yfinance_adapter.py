"""yfinance adapter — забирает DXY/VIX/SPX/NDX/Gold/Oil/yields из Yahoo Finance.

Источник: yfinance Python library (бесплатно, скрапит Yahoo).
Используется для построения MacroSnapshot для Macro Analyst (Layer 3).

Mapping Yahoo тикеров:
- DXY (USD Index) → "DX-Y.NYB"
- VIX (S&P volatility) → "^VIX"
- S&P 500 → "^GSPC" (spot) / "ES=F" (futures)
- NASDAQ-100 → "^NDX"
- Gold → "GC=F" (futures)
- Crude oil → "CL=F" (WTI futures)
- 10Y yield → "^TNX" (×10 = %)

Замечания:
- yfinance даёт delayed (~15 min) — для нашего use case (Macro раз в час) OK
- Иногда тикеры возвращают NaN/None — обрабатываем как warning + skip
- Сетевые ошибки логируются + не валят MacroSnapshot (Optional поля)
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Protocol

from parsers.macro.models import MacroSnapshot, YfinanceQuote

logger = logging.getLogger(__name__)

# Mapping: наше внутреннее имя → Yahoo тикер
_YAHOO_TICKERS: dict[str, str] = {
    "dxy": "DX-Y.NYB",
    "vix": "^VIX",
    "spx": "^GSPC",
    "ndx": "^NDX",
    "gold": "GC=F",
    "oil": "CL=F",
    "yield_10y": "^TNX",
}


class YahooFetcher(Protocol):
    """Контракт реального fetcher'а из yfinance.

    Используем Protocol чтобы тесты могли подменять реальный yf.Ticker
    на мок без установки yfinance библиотеки.

    Возвращает {symbol: YfinanceQuote} для всех запрошенных тикеров.
    """

    def fetch(self, tickers: list[str]) -> dict[str, YfinanceQuote]: ...


class YfinanceAdapter:
    """Адаптер MacroSnapshot из Yahoo Finance.

    Конструктор принимает ``fetcher`` (YahooFetcher Protocol) — это DI
    позволяет тестам подменять без зависимости от внешнего сервиса.
    Production: YfinanceLibFetcher (отдельно).

    Использование::

        adapter = YfinanceAdapter(fetcher=YfinanceLibFetcher())
        snap = adapter.snapshot()
        # → MacroSnapshot с заполненными dxy/vix/spx/etc.
    """

    def __init__(self, fetcher: YahooFetcher) -> None:
        self._fetcher = fetcher

    def snapshot(self) -> MacroSnapshot:
        """Собрать актуальный MacroSnapshot.

        Если какой-то тикер недоступен — соответствующее поле = None,
        warning записывается в MacroSnapshot.warnings.
        """
        warnings: list[str] = []
        tickers = list(_YAHOO_TICKERS.values())
        try:
            quotes = self._fetcher.fetch(tickers)
        except Exception as e:
            logger.error("yfinance fetch failed: %s", e)
            return MacroSnapshot(
                timestamp_ms=int(time.time() * 1000),
                warnings=(f"yfinance fetch failed: {e}",),
            )

        values: dict[str, Decimal | None] = {}
        changes: dict[str, Decimal | None] = {}
        for internal_name, yahoo_ticker in _YAHOO_TICKERS.items():
            quote = quotes.get(yahoo_ticker)
            if quote is None:
                warnings.append(f"yfinance: {yahoo_ticker} not in response")
                values[internal_name] = None
                changes[internal_name] = None
            else:
                values[internal_name] = quote.last
                changes[internal_name] = quote.change_pct_24h

        # ^TNX from Yahoo приходит как 4.25 (имеется в виду %), не /100
        return MacroSnapshot(
            timestamp_ms=int(time.time() * 1000),
            dxy=values.get("dxy"),
            dxy_change_24h_pct=changes.get("dxy"),
            vix=values.get("vix"),
            vix_change_24h_pct=changes.get("vix"),
            spx=values.get("spx"),
            ndx=values.get("ndx"),
            gold=values.get("gold"),
            oil=values.get("oil"),
            yield_10y=values.get("yield_10y"),
            warnings=tuple(warnings),
        )
