"""YahooHttpFetcher — реальная имплементация YahooFetcher Protocol через httpx.

Использует публичный quote endpoint Yahoo Finance — авторизация не нужна.
Лёгкая альтернатива yfinance (без pandas/numpy зависимостей).

Endpoint: GET https://query1.finance.yahoo.com/v7/finance/quote?symbols=...
Возвращает JSON с полями: regularMarketPrice, regularMarketChangePercent,
regularMarketVolume, regularMarketTime (Unix seconds).

Yahoo иногда блочит boт-like запросы; используем User-Agent похожий на
браузер + follow_redirects. Если падает 429 / 401 — графенно отдаём пустой
dict (YfinanceAdapter тогда вернёт None-fields в MacroSnapshot, Layer 3
prompt обработает).
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

import httpx

from parsers.macro.models import YfinanceQuote

logger = logging.getLogger(__name__)

_YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT_S = 10.0


class YahooHttpFetcher:
    """Production YahooFetcher через HTTP GET на Yahoo quote API.

    Использование::

        fetcher = YahooHttpFetcher()
        quotes = fetcher.fetch(["DX-Y.NYB", "^VIX", "^GSPC"])
        # → {"DX-Y.NYB": YfinanceQuote(...), "^VIX": ...}

    DI httpx.Client опциональный — если не передан, создаётся свой с
    timeout и пользовательским User-Agent.
    """

    def __init__(
        self,
        *,
        base_url: str = _YAHOO_QUOTE_URL,
        client: httpx.Client | None = None,
        timeout_s: float = _TIMEOUT_S,
    ) -> None:
        self._base_url = base_url
        self._client = client
        self._owns_client = client is None
        self._timeout_s = timeout_s

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                timeout=self._timeout_s,
                headers={"User-Agent": _BROWSER_UA, "Accept": "application/json"},
                follow_redirects=True,
            )
        return self._client

    def fetch(self, tickers: list[str]) -> dict[str, YfinanceQuote]:
        """Один HTTP запрос на все тикеры (Yahoo поддерживает batch)."""
        if not tickers:
            return {}
        client = self._get_client()
        result: dict[str, YfinanceQuote] = {}
        try:
            resp = client.get(self._base_url, params={"symbols": ",".join(tickers)})
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "Yahoo quote HTTP %s for %s: %s",
                e.response.status_code,
                tickers,
                e,
            )
            return {}
        except Exception as e:
            logger.warning("Yahoo quote fetch failed: %s", e)
            return {}

        try:
            data = resp.json()
        except ValueError:
            logger.warning("Yahoo quote returned non-JSON")
            return {}

        results = data.get("quoteResponse", {}).get("result", [])
        for item in results:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol")
            if not symbol:
                continue
            quote = _parse_quote(symbol, item)
            if quote is not None:
                result[symbol] = quote

        if not result and tickers:
            logger.info("Yahoo quote: no parseable items in response")
        return result


def _parse_quote(symbol: str, item: dict[str, object]) -> YfinanceQuote | None:
    """Сконвертировать Yahoo quote response item → YfinanceQuote.

    Возвращает None если последняя цена отсутствует (тикер невалидный или
    маркет закрыт без previous close).
    """
    last_raw = item.get("regularMarketPrice")
    if last_raw is None:
        last_raw = item.get("postMarketPrice") or item.get("preMarketPrice")
    if last_raw is None:
        return None

    try:
        last = Decimal(str(last_raw))
    except (InvalidOperation, TypeError, ValueError):
        return None

    timestamp_raw = item.get("regularMarketTime")
    timestamp_s = 0
    if timestamp_raw is not None:
        try:
            timestamp_s = int(str(timestamp_raw))
        except (TypeError, ValueError):
            timestamp_s = 0
    if timestamp_s <= 0:
        import time

        timestamp_s = int(time.time())
    timestamp_ms = timestamp_s * 1000

    change_pct = _maybe_decimal(item.get("regularMarketChangePercent"))
    volume = _maybe_decimal(item.get("regularMarketVolume"))

    return YfinanceQuote(
        symbol=symbol,
        timestamp_ms=timestamp_ms,
        last=last,
        change_pct_24h=change_pct,
        volume_24h=volume,
    )


def _maybe_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
