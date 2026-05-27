"""Bybit V5 klines downloader (public, без auth, без денег).

Парный по формату с ``download_klines.py`` (BingX) — пишет тот же
``Kline``-jsonl (``adapters.bingx.models.Kline``), значит уже
существующие ``run_backtest`` / ``walk_forward`` напрямую читают
Bybit-данные без правок.

Зачем: BingX моложе и по многим парам имеет меньше истории, чем
Bybit. Для backtest/probe берём более глубокий источник.

⚠️ Bybit блокирует cloud-IP некоторых регионов (включая контейнеры
этой сессии — 403 даже на public). Скрипт запускается на VPS или
локально, где Bybit доступен. Pure-парсер протестирован без сети.

Запуск:
    .venv/bin/python -m scripts.download_klines_bybit \\
        --symbol BTCUSDT --interval 15 --months 12
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from adapters.bingx.models import Kline

_BASE_URL = "https://api.bybit.com/v5/market/kline"
_UA = "Mozilla/5.0 (compatible; crypto-bot/1.0)"
_MAX_LIMIT = 1000
_DAY_MS = 86_400_000

# Bybit V5 intervals: minutes integers + D/W/M
_INTERVAL_MS = {
    "1": 60_000,
    "3": 180_000,
    "5": 300_000,
    "15": 900_000,
    "30": 1_800_000,
    "60": 3_600_000,
    "120": 7_200_000,
    "240": 14_400_000,
    "360": 21_600_000,
    "720": 43_200_000,
    "D": 86_400_000,
    "W": 7 * 86_400_000,
    "M": 30 * 86_400_000,
}


def _slug(bybit_symbol: str, interval: str) -> str:
    # BTCUSDT → btc-usdt; для маппинга с существующими файлами BingX (btc-usdt-15m).
    s = bybit_symbol.lower()
    if s.endswith("usdt"):
        s = s[:-4] + "-usdt"
    iv_suf = f"{interval}m" if interval.isdigit() else interval.lower()
    return f"{s}-{iv_suf}"


def parse_kline_payload(payload: dict[str, Any]) -> list[dict[str, str | int]]:
    """Bybit V5 kline → Kline-jsonl rows.

    Response: ``result.list = [[startMs, o, h, l, c, vol, turnover], ...]``
    в обратном порядке (новые первыми). Возвращаем по возрастанию ts.
    """
    out: list[dict[str, str | int]] = []
    res = payload.get("result") or {}
    rows = res.get("list") or []
    for r in rows:
        if not isinstance(r, list) or len(r) < 6:
            continue
        out.append(
            {
                "time": int(r[0]),
                "open": str(r[1]),
                "high": str(r[2]),
                "low": str(r[3]),
                "close": str(r[4]),
                "volume": str(r[5]),
            }
        )
    out.sort(key=lambda x: x["time"])
    return out


def fetch_klines_window(
    symbol: str, interval: str, *, start_ms: int, end_ms: int, category: str = "linear"
) -> list[dict[str, str | int]]:
    """Один запрос за окно (≤1000 баров). Сеть."""
    qs = urllib.parse.urlencode(
        {
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "start": start_ms,
            "end": end_ms,
            "limit": _MAX_LIMIT,
        }
    )
    req = urllib.request.Request(f"{_BASE_URL}?{qs}", headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return parse_kline_payload(json.loads(r.read().decode("utf-8")))


def fetch_klines_range(
    symbol: str, interval: str, *, start_ms: int, end_ms: int, category: str = "linear"
) -> list[dict[str, str | int]]:
    """Полный диапазон, пагинация по окнам."""
    iv_ms = _INTERVAL_MS.get(interval)
    if iv_ms is None:
        return fetch_klines_window(
            symbol, interval, start_ms=start_ms, end_ms=end_ms, category=category
        )
    out: dict[int, dict[str, str | int]] = {}
    cursor = start_ms
    while cursor < end_ms:
        win_end = min(cursor + iv_ms * _MAX_LIMIT, end_ms)
        batch = fetch_klines_window(
            symbol, interval, start_ms=cursor, end_ms=win_end, category=category
        )
        if not batch:
            break
        for row in batch:
            out[int(row["time"])] = row
        cursor = int(batch[-1]["time"]) + iv_ms
        time.sleep(0.1)  # щадящий темп
    return sorted(out.values(), key=lambda r: r["time"])


def main() -> None:
    p = argparse.ArgumentParser(description="Bybit V5 klines → Kline-jsonl (BingX-совместимо)")
    p.add_argument("--symbol", required=True, help="например BTCUSDT")
    p.add_argument(
        "--interval", default="15", help="1/3/5/15/30/60/120/240/360/720/D/W/M (V5 формат)"
    )
    p.add_argument("--months", type=int, default=12)
    p.add_argument("--category", default="linear", choices=["linear", "inverse", "spot"])
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - args.months * 30 * _DAY_MS
    out = args.out or Path("data/candles") / f"{_slug(args.symbol, args.interval)}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = fetch_klines_range(
        args.symbol, args.interval, start_ms=start_ms, end_ms=end_ms, category=args.category
    )

    # Sanity-валидация через Kline-модель (тот же тип, что BingX).
    valid: list[dict[str, str | int]] = []
    for row in rows:
        try:
            Kline.model_validate(row)
            valid.append(row)
        except Exception as e:
            print(f"skip invalid row {row.get('time')}: {e}")

    with out.open("w", encoding="utf-8") as f:
        for row in valid:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
    span_days = (valid[-1]["time"] - valid[0]["time"]) / _DAY_MS if valid else 0  # type: ignore[operator]
    print(f"saved {len(valid)} candles to {out} ({span_days:.1f} days)")


if __name__ == "__main__":
    main()
