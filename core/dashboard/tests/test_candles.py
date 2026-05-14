"""Unit-тесты ``CandlesFetcher`` + ``/api/candles`` endpoint."""

from __future__ import annotations

import pathlib

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from core.dashboard.api import create_app
from core.dashboard.candles import CandlesFetcher, candle_to_dict

_SAMPLE_KLINES = {
    "code": 0,
    "data": [
        {
            "time": 1_700_000_900_000,
            "open": "80500",
            "high": "80700",
            "low": "80450",
            "close": "80650",
            "volume": "12.5",
        },
        {
            "time": 1_700_000_000_000,
            "open": "80400",
            "high": "80550",
            "low": "80350",
            "close": "80500",
            "volume": "10.1",
        },
    ],
}


def test_get_candles_happy_path() -> None:
    with respx.mock(base_url="https://open-api.bingx.com") as mock:
        mock.get("/openApi/swap/v3/quote/klines").mock(
            return_value=httpx.Response(200, json=_SAMPLE_KLINES)
        )
        fetcher = CandlesFetcher()
        cs = fetcher.get("BTC-USDT", "15m", 100)
    assert len(cs) == 2
    # ASC ordered
    assert cs[0].time_ms < cs[1].time_ms
    assert cs[0].close == 80500.0
    assert cs[1].close == 80650.0


def test_invalid_interval_raises() -> None:
    fetcher = CandlesFetcher()
    with pytest.raises(ValueError, match="Invalid interval"):
        fetcher.get("BTC-USDT", "7m", 100)


def test_invalid_limit_raises() -> None:
    fetcher = CandlesFetcher()
    with pytest.raises(ValueError, match="limit must be"):
        fetcher.get("BTC-USDT", "15m", 0)
    with pytest.raises(ValueError, match="limit must be"):
        fetcher.get("BTC-USDT", "15m", 2000)


def test_caches_within_ttl() -> None:
    call_count = {"n": 0}

    def _handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json=_SAMPLE_KLINES)

    with respx.mock(base_url="https://open-api.bingx.com") as mock:
        mock.get("/openApi/swap/v3/quote/klines").mock(side_effect=_handler)
        fetcher = CandlesFetcher(ttl_s=60.0)
        fetcher.get("BTC-USDT", "15m", 100)
        first = call_count["n"]
        fetcher.get("BTC-USDT", "15m", 100)
        assert call_count["n"] == first  # cached


def test_handles_http_error() -> None:
    with respx.mock(base_url="https://open-api.bingx.com") as mock:
        mock.get("/openApi/swap/v3/quote/klines").mock(
            return_value=httpx.Response(500, json={"code": 500})
        )
        fetcher = CandlesFetcher()
        cs = fetcher.get("BTC-USDT", "15m", 100)
    assert cs == []


def test_candle_to_dict_format() -> None:
    """Lightweight Charts ожидает time в unix seconds + OHLC."""
    from core.dashboard.candles import Candle

    c = Candle(time_ms=1_700_000_900_000, open=1.0, high=2.0, low=0.5, close=1.5, volume=100)
    d = candle_to_dict(c)
    assert d["time"] == 1_700_000_900  # ms → s
    assert d["open"] == 1.0
    assert d["close"] == 1.5


def test_candles_endpoint(tmp_path: pathlib.Path) -> None:
    with respx.mock(assert_all_called=False, base_url="https://open-api.bingx.com") as mock:
        mock.get("/openApi/swap/v3/quote/klines").mock(
            return_value=httpx.Response(200, json=_SAMPLE_KLINES)
        )
        app = create_app(
            outcomes_db=tmp_path / "x.sqlite",
            halt_flag_file=None,
            heartbeat_file=None,
        )
        client = TestClient(app)
        resp = client.get("/api/candles?symbol=BTC-USDT&interval=15m&limit=50")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "BTC-USDT"
    assert data["interval"] == "15m"
    assert len(data["candles"]) == 2
    assert "time" in data["candles"][0]
    assert "close" in data["candles"][0]


def test_candles_endpoint_invalid_interval(tmp_path: pathlib.Path) -> None:
    app = create_app(
        outcomes_db=tmp_path / "x.sqlite",
        halt_flag_file=None,
        heartbeat_file=None,
    )
    client = TestClient(app)
    resp = client.get("/api/candles?interval=invalid")
    assert resp.status_code == 400
