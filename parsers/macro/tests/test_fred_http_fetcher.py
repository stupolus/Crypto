"""Unit-тесты ``FREDHttpFetcher``.

Используем respx для mocking httpx — никаких реальных вызовов FRED API.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import httpx
import pytest
import respx

from parsers.macro import FREDHttpFetcher


def _observations_response(value: str) -> dict[str, Any]:
    """Шаблон FRED API response."""
    return {
        "realtime_start": "2026-05-13",
        "realtime_end": "2026-05-13",
        "observation_start": "2026-05-13",
        "observation_end": "2026-05-13",
        "count": 1,
        "offset": 0,
        "limit": 1,
        "observations": [
            {
                "realtime_start": "2026-05-13",
                "realtime_end": "2026-05-13",
                "date": "2026-05-13",
                "value": value,
            }
        ],
    }


def test_fred_http_fetcher_single_series() -> None:
    with httpx.Client() as client, respx.mock(base_url="https://api.stlouisfed.org") as mock:
        mock.get("/fred/series/observations").mock(
            return_value=httpx.Response(200, json=_observations_response("5.33"))
        )
        fetcher = FREDHttpFetcher(api_key="test-key", client=client)
        result = fetcher.fetch_latest(["DFF"])
    assert result == {"DFF": Decimal("5.33")}


def test_fred_http_fetcher_handles_missing_dot() -> None:
    """FRED использует '.' для missing values — skip."""
    with httpx.Client() as client, respx.mock(base_url="https://api.stlouisfed.org") as mock:
        mock.get("/fred/series/observations").mock(
            return_value=httpx.Response(200, json=_observations_response("."))
        )
        fetcher = FREDHttpFetcher(api_key="test-key", client=client)
        result = fetcher.fetch_latest(["DFF"])
    assert result == {}


def test_fred_http_fetcher_handles_http_error() -> None:
    """HTTP error → skip series, не raises."""
    with httpx.Client() as client, respx.mock(base_url="https://api.stlouisfed.org") as mock:
        mock.get("/fred/series/observations").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        fetcher = FREDHttpFetcher(api_key="test-key", client=client)
        result = fetcher.fetch_latest(["INVALID_SERIES"])
    assert result == {}


def test_fred_http_fetcher_empty_observations() -> None:
    response: dict[str, Any] = _observations_response("0")
    response["observations"] = []  # пустой список
    with httpx.Client() as client, respx.mock(base_url="https://api.stlouisfed.org") as mock:
        mock.get("/fred/series/observations").mock(return_value=httpx.Response(200, json=response))
        fetcher = FREDHttpFetcher(api_key="test-key", client=client)
        result = fetcher.fetch_latest(["DFF"])
    assert result == {}


def test_fred_http_fetcher_invalid_value() -> None:
    """Если value не парсится как Decimal — skip с warning."""
    with httpx.Client() as client, respx.mock(base_url="https://api.stlouisfed.org") as mock:
        mock.get("/fred/series/observations").mock(
            return_value=httpx.Response(200, json=_observations_response("not a number"))
        )
        fetcher = FREDHttpFetcher(api_key="test-key", client=client)
        result = fetcher.fetch_latest(["DFF"])
    assert result == {}


def test_fred_http_fetcher_empty_api_key_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty api_key"):
        FREDHttpFetcher(api_key="")


def test_fred_http_fetcher_sends_correct_params() -> None:
    """Проверяем что params включают api_key, file_type, sort_order, limit."""
    with httpx.Client() as client, respx.mock(base_url="https://api.stlouisfed.org") as mock:
        route = mock.get("/fred/series/observations").mock(
            return_value=httpx.Response(200, json=_observations_response("5.33"))
        )
        fetcher = FREDHttpFetcher(api_key="abc-test-key", client=client)
        fetcher.fetch_latest(["DFF"])
    assert route.called
    req = route.calls.last.request
    assert "series_id=DFF" in str(req.url)
    assert "api_key=abc-test-key" in str(req.url)
    assert "file_type=json" in str(req.url)
    assert "sort_order=desc" in str(req.url)
    assert "limit=1" in str(req.url)


def test_fred_http_fetcher_multiple_series() -> None:
    with httpx.Client() as client, respx.mock(base_url="https://api.stlouisfed.org") as mock:
        # FRED Mock returns same value для всех серий — упрощение теста
        mock.get("/fred/series/observations").mock(
            return_value=httpx.Response(200, json=_observations_response("3.8"))
        )
        fetcher = FREDHttpFetcher(api_key="test-key", client=client)
        result = fetcher.fetch_latest(["DFF", "UNRATE", "CPIAUCSL"])
    # Все 3 series в результате (mock возвращает то же значение для всех)
    assert len(result) == 3
    assert all(v == Decimal("3.8") for v in result.values())
