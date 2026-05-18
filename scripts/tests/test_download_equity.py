"""Тест парсинга Yahoo chart → Kline-jsonl (без сети)."""

from __future__ import annotations

from adapters.bingx.models import Kline
from scripts.download_equity import _slug, parse_chart_payload

_PAYLOAD = {
    "chart": {
        "result": [
            {
                "timestamp": [946684800, 946771200, 946857600],
                "indicators": {
                    "quote": [
                        {
                            "open": [100.0, 101.5, None],
                            "high": [102.0, 103.0, 104.0],
                            "low": [99.0, 100.5, 101.0],
                            "close": [101.0, 102.5, None],
                            "volume": [1000, None, 2000],
                        }
                    ]
                },
            }
        ],
        "error": None,
    }
}


def test_parse_skips_null_bars_and_converts_seconds_to_ms() -> None:
    rows = parse_chart_payload(_PAYLOAD, "^GSPC")
    # Третий бар отброшен (open/close = None).
    assert len(rows) == 2
    assert rows[0]["time"] == 946684800 * 1000
    assert rows[0]["open"] == "100.0"
    # None volume → "0".
    assert rows[1]["volume"] == "0"
    assert rows[1]["time"] == 946771200 * 1000


def test_rows_are_kline_compatible() -> None:
    for raw in parse_chart_payload(_PAYLOAD, "^GSPC"):
        Kline.model_validate(raw)


def test_rows_sorted_by_time() -> None:
    rows = parse_chart_payload(_PAYLOAD, "^GSPC")
    times = [r["time"] for r in rows]
    assert times == sorted(times)


def test_slug() -> None:
    assert _slug("^GSPC") == "gspc"
    assert _slug("AAPL") == "aapl"
    assert _slug("BRK.B") == "brk-b"
