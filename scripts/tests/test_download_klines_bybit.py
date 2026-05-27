"""Тесты pure-логики bybit-downloader (без сети)."""

from __future__ import annotations

from adapters.bingx.models import Kline
from scripts.download_klines_bybit import _slug, parse_kline_payload


def test_slug_btcusdt() -> None:
    assert _slug("BTCUSDT", "15") == "btc-usdt-15m"
    assert _slug("ETHUSDT", "60") == "eth-usdt-60m"
    assert _slug("BTCUSDT", "D") == "btc-usdt-d"


def test_parse_kline_payload_orders_asc_and_skips_garbage() -> None:
    # Bybit отдаёт новые-первыми; парсер должен сортировать по возрастанию.
    payload = {
        "result": {
            "list": [
                ["1700000300000", "100.3", "100.5", "100.2", "100.4", "1.5", "150"],
                ["1700000200000", "100.2", "100.4", "100.1", "100.3", "1.2", "120"],
                ["1700000100000", "100.1", "100.3", "100.0", "100.2", "1.0", "100"],
                "garbage",  # будет отброшено
                ["bad-row"],  # слишком короткая → отброшено
            ]
        }
    }
    rows = parse_kline_payload(payload)
    assert [r["time"] for r in rows] == [1700000100000, 1700000200000, 1700000300000]
    assert rows[0] == {
        "time": 1700000100000,
        "open": "100.1",
        "high": "100.3",
        "low": "100.0",
        "close": "100.2",
        "volume": "1.0",
    }


def test_parse_empty() -> None:
    assert parse_kline_payload({"result": {"list": []}}) == []
    assert parse_kline_payload({}) == []


def test_rows_validate_as_bingx_kline() -> None:
    """Формат совместим: BingX Kline.model_validate проходит."""
    payload = {
        "result": {
            "list": [
                ["1700000100000", "100.1", "100.3", "100.0", "100.2", "1.0", "100"],
            ]
        }
    }
    for row in parse_kline_payload(payload):
        Kline.model_validate(row)  # не падает
