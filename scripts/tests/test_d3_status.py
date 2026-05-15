"""Unit-тесты парсера D3 статус-скрипта."""

from __future__ import annotations

from pathlib import Path

from scripts.d3_status import _format_runtime, _parse_log

_SAMPLE_LOG = """\
2026-05-12 08:00:01,000 INFO __main__ runner starting
2026-05-12 08:30:12,528 INFO __main__ candle closed: BTC-USDT o=80780.2 c=80832.6 h=80899.7 l=80718.6
2026-05-12 08:45:20,409 INFO __main__ candle closed: BTC-USDT o=80832.6 c=80918.5 h=80925.0 l=80802.7
2026-05-12 08:47:21,158 WARNING adapters.bingx.websocket BingX WS resubscribe attempt 1/3 failed channel=BTC-USDT@kline_15m: ack timeout
2026-05-12 09:00:11,292 ERROR __main__ something bad
2026-05-12 09:15:00,000 INFO __main__ signal: long entry @ 80700
"""


def test_parse_log_counts_closes(tmp_path: Path) -> None:
    p = tmp_path / "btc.log"
    p.write_text(_SAMPLE_LOG)
    stats = _parse_log(p)
    assert stats.closes == 2
    assert stats.signals == 1
    assert stats.errors == 1
    assert stats.ws_resubscribe_failures == 1
    assert stats.last_close_price == "80918.5"
    assert stats.last_close_ts == "2026-05-12 08:45:20"


def test_parse_log_empty(tmp_path: Path) -> None:
    p = tmp_path / "missing.log"
    stats = _parse_log(p)
    assert stats.closes == 0
    assert stats.last_close_price is None


def test_parse_log_first_last_timestamps(tmp_path: Path) -> None:
    p = tmp_path / "btc.log"
    p.write_text(_SAMPLE_LOG)
    stats = _parse_log(p)
    assert stats.first_ts == "2026-05-12 08:00:01"
    assert stats.last_ts == "2026-05-12 09:15:00"


def test_format_runtime_hours() -> None:
    assert _format_runtime("2026-05-12 08:00:00", "2026-05-12 11:00:00") == "3.0h"
    assert _format_runtime("2026-05-12 08:00:00", "2026-05-12 09:30:00") == "1.5h"


def test_format_runtime_minutes_for_under_hour() -> None:
    assert _format_runtime("2026-05-12 08:00:00", "2026-05-12 08:25:00") == "25m"


def test_format_runtime_invalid_input() -> None:
    assert _format_runtime(None, None) == "?"
    assert _format_runtime("not-a-date", "2026-05-12 08:00:00") == "?"
