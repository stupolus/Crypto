"""Одной командой — статус D3 dry-run-free на VST.

Читает ``ops/logs/d3/*.log`` и ``ops/logs/d3/*-metrics.jsonl`` и печатает
сводку: closes, signals, orders, errors по каждому символу + аггрегаты.

Запуск:
    .venv/bin/python -m scripts.d3_status

Опции:
    --logs-dir DIR  — переопределить директорию логов (default ops/logs/d3)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_CLOSE_RE = re.compile(r"candle closed: (\S+) o=(\S+) c=(\S+) h=(\S+) l=(\S+)")
_SIGNAL_RE = re.compile(r"signal:|order placed|order filled|order rejected")
_ERROR_RE = re.compile(r"ERROR|CRITICAL|Traceback")


@dataclass
class SymbolStats:
    symbol: str
    closes: int = 0
    signals: int = 0
    orders_placed: int = 0
    orders_filled: int = 0
    orders_rejected: int = 0
    errors: int = 0
    ws_resubscribe_failures: int = 0
    last_close_ts: str | None = None
    last_close_price: str | None = None
    first_ts: str | None = None
    last_ts: str | None = None
    interesting: list[str] = field(default_factory=list)


def _parse_log(path: Path) -> SymbolStats:
    sym = path.stem.upper()
    stats = SymbolStats(symbol=sym)
    if not path.exists():
        return stats
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m_ts = _TS_RE.match(line)
        if m_ts:
            ts = m_ts.group(1)
            if stats.first_ts is None:
                stats.first_ts = ts
            stats.last_ts = ts
        if "candle closed:" in line:
            stats.closes += 1
            m = _CLOSE_RE.search(line)
            if m:
                stats.last_close_ts = m_ts.group(1) if m_ts else None
                stats.last_close_price = m.group(3)
        if "signal:" in line:
            stats.signals += 1
        if "order placed" in line:
            stats.orders_placed += 1
        if "order filled" in line:
            stats.orders_filled += 1
        if "order rejected" in line:
            stats.orders_rejected += 1
        if "resubscribe" in line and ("failed" in line or "permanently" in line):
            stats.ws_resubscribe_failures += 1
        if _ERROR_RE.search(line):
            stats.errors += 1
            if len(stats.interesting) < 5:
                stats.interesting.append(line.strip()[:200])
    return stats


def _read_last_metrics(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    last: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue
    return last


def _format_runtime(first: str | None, last: str | None) -> str:
    if not first or not last:
        return "?"
    try:
        f = datetime.strptime(first, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return "?"
    delta = last_dt - f
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"{delta.total_seconds() / 60:.0f}m"
    return f"{hours:.1f}h"


def main() -> int:
    parser = argparse.ArgumentParser(description="D3 status snapshot")
    parser.add_argument("--logs-dir", default="ops/logs/d3", type=Path)
    args = parser.parse_args()

    logs = sorted(args.logs_dir.glob("*.log"))
    if not logs:
        print(f"no .log files in {args.logs_dir}", file=sys.stderr)
        return 1

    per_symbol: list[SymbolStats] = [_parse_log(p) for p in logs]

    header = (
        f"{'Symbol':10} | {'Runtime':8} | {'Closes':6} | {'Signals':7} | "
        f"{'Orders':14} | {'Errors':6} | {'Last close (UTC)':19} | {'Last price':10}"
    )
    print(header)
    print("-" * len(header))
    for s in per_symbol:
        orders = f"{s.orders_placed}P/{s.orders_filled}F/{s.orders_rejected}R"
        runtime = _format_runtime(s.first_ts, s.last_ts)
        last_close = s.last_close_ts or "—"
        last_price = s.last_close_price or "—"
        print(
            f"{s.symbol:10} | {runtime:8} | {s.closes:6d} | {s.signals:7d} | "
            f"{orders:14} | {s.errors:6d} | {last_close:19} | {last_price:10}"
        )

    print()
    print("Aggregated:")
    print(f"  symbols: {len(per_symbol)}")
    print(f"  total closes: {sum(s.closes for s in per_symbol)}")
    print(f"  total signals: {sum(s.signals for s in per_symbol)}")
    print(f"  total orders: {sum(s.orders_placed for s in per_symbol)}")
    print(f"  total errors: {sum(s.errors for s in per_symbol)}")
    ws_fails = sum(s.ws_resubscribe_failures for s in per_symbol)
    if ws_fails:
        print(f"  WS resubscribe events: {ws_fails}")

    # Если есть metrics — показать последнюю запись по эквити.
    print()
    print("Last metrics snapshot:")
    for p in args.logs_dir.glob("*-metrics.jsonl"):
        last = _read_last_metrics(p)
        if last:
            print(f"  {p.stem}: {last}")

    # Errors detail.
    interesting = [(s.symbol, e) for s in per_symbol for e in s.interesting]
    if interesting:
        print()
        print(f"Error samples (top {len(interesting)}):")
        for sym, e in interesting:
            print(f"  [{sym}] {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
