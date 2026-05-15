"""Unit-тесты ``YahooHttpFetcher`` — mock через respx."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import respx

from parsers.macro.yahoo_http_fetcher import YahooHttpFetcher


def _quote_response(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"quoteResponse": {"result": items, "error": None}}


def _btc_item(symbol: str = "DX-Y.NYB", price: float = 105.42) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "regularMarketPrice": price,
        "regularMarketChangePercent": 0.42,
        "regularMarketVolume": 1_234_567,
        "regularMarketTime": 1_700_000_000,
    }


def test_fetch_single_ticker() -> None:
    with (
        httpx.Client() as client,
        respx.mock(base_url="https://query1.finance.yahoo.com") as mock,
    ):
        mock.get("/v7/finance/quote").mock(
            return_value=httpx.Response(200, json=_quote_response([_btc_item("DX-Y.NYB", 105.42)]))
        )
        fetcher = YahooHttpFetcher(client=client)
        quotes = fetcher.fetch(["DX-Y.NYB"])
    assert "DX-Y.NYB" in quotes
    q = quotes["DX-Y.NYB"]
    assert q.last == Decimal("105.42")
    assert q.change_pct_24h == Decimal("0.42")
    assert q.timestamp_ms == 1_700_000_000_000


def test_fetch_multiple_tickers() -> None:
    items = [
        _btc_item("DX-Y.NYB", 105.42),
        _btc_item("^VIX", 14.30),
        _btc_item("^GSPC", 5800.10),
    ]
    with (
        httpx.Client() as client,
        respx.mock(base_url="https://query1.finance.yahoo.com") as mock,
    ):
        mock.get("/v7/finance/quote").mock(
            return_value=httpx.Response(200, json=_quote_response(items))
        )
        fetcher = YahooHttpFetcher(client=client)
        quotes = fetcher.fetch(["DX-Y.NYB", "^VIX", "^GSPC"])
    assert len(quotes) == 3
    assert quotes["^GSPC"].last == Decimal("5800.10")


def test_empty_tickers_returns_empty() -> None:
    fetcher = YahooHttpFetcher()
    assert fetcher.fetch([]) == {}


def test_handles_http_error_gracefully() -> None:
    with (
        httpx.Client() as client,
        respx.mock(base_url="https://query1.finance.yahoo.com") as mock,
    ):
        mock.get("/v7/finance/quote").mock(
            return_value=httpx.Response(429, json={"error": "rate limited"})
        )
        fetcher = YahooHttpFetcher(client=client)
        quotes = fetcher.fetch(["DX-Y.NYB"])
    assert quotes == {}


def test_handles_unauthorized() -> None:
    with (
        httpx.Client() as client,
        respx.mock(base_url="https://query1.finance.yahoo.com") as mock,
    ):
        mock.get("/v7/finance/quote").mock(
            return_value=httpx.Response(401, json={"error": "unauthorized"})
        )
        fetcher = YahooHttpFetcher(client=client)
        quotes = fetcher.fetch(["^VIX"])
    assert quotes == {}


def test_handles_non_json_response() -> None:
    with (
        httpx.Client() as client,
        respx.mock(base_url="https://query1.finance.yahoo.com") as mock,
    ):
        mock.get("/v7/finance/quote").mock(
            return_value=httpx.Response(200, text="<html>blocked</html>")
        )
        fetcher = YahooHttpFetcher(client=client)
        quotes = fetcher.fetch(["^VIX"])
    assert quotes == {}


def test_skips_items_without_price() -> None:
    """Если у тикера нет regularMarketPrice — пропускаем."""
    items = [
        {"symbol": "BAD_TICKER", "regularMarketChangePercent": 1.0},
        _btc_item("^VIX", 15.0),
    ]
    with (
        httpx.Client() as client,
        respx.mock(base_url="https://query1.finance.yahoo.com") as mock,
    ):
        mock.get("/v7/finance/quote").mock(
            return_value=httpx.Response(200, json=_quote_response(items))
        )
        fetcher = YahooHttpFetcher(client=client)
        quotes = fetcher.fetch(["BAD_TICKER", "^VIX"])
    assert "BAD_TICKER" not in quotes
    assert "^VIX" in quotes


def test_falls_back_to_post_market_price() -> None:
    """Если regular market закрыт, берём postMarketPrice."""
    item = {
        "symbol": "^VIX",
        "postMarketPrice": 14.80,
        "regularMarketTime": 1_700_000_000,
    }
    with (
        httpx.Client() as client,
        respx.mock(base_url="https://query1.finance.yahoo.com") as mock,
    ):
        mock.get("/v7/finance/quote").mock(
            return_value=httpx.Response(200, json=_quote_response([item]))
        )
        fetcher = YahooHttpFetcher(client=client)
        quotes = fetcher.fetch(["^VIX"])
    assert quotes["^VIX"].last == Decimal("14.80")


def test_missing_timestamp_uses_now() -> None:
    """Если regularMarketTime отсутствует — берём текущее время."""
    item = {"symbol": "^VIX", "regularMarketPrice": 15.0}
    with (
        httpx.Client() as client,
        respx.mock(base_url="https://query1.finance.yahoo.com") as mock,
    ):
        mock.get("/v7/finance/quote").mock(
            return_value=httpx.Response(200, json=_quote_response([item]))
        )
        fetcher = YahooHttpFetcher(client=client)
        quotes = fetcher.fetch(["^VIX"])
    assert quotes["^VIX"].timestamp_ms > 1_700_000_000_000


def test_sends_correct_params() -> None:
    """Проверка что запрос отправляет batch symbols в одном запросе."""
    with (
        httpx.Client() as client,
        respx.mock(base_url="https://query1.finance.yahoo.com") as mock,
    ):
        route = mock.get("/v7/finance/quote").mock(
            return_value=httpx.Response(200, json=_quote_response([_btc_item()]))
        )
        fetcher = YahooHttpFetcher(client=client)
        fetcher.fetch(["DX-Y.NYB", "^VIX", "^GSPC"])
    assert route.called
    request = route.calls.last.request
    assert "symbols=DX-Y.NYB%2C%5EVIX%2C%5EGSPC" in str(request.url)
