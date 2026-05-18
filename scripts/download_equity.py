"""Скачивание дневной истории TradFi-инструментов с Yahoo Finance.

Зачем: BingX-контракты на S&P500/акции — синтетика с короткой историей
(см. plans/26). Edge ищем на реальном underlying по длинной истории.

Yahoo chart API (`period1=0&period2=now&interval=1d`) отдаёт десятки лет
дневных баров. Сохраняем в формат ``Kline``-jsonl, совместимый с
``scripts.run_backtest`` / ``scripts.walk_forward``.

Запуск:
    .venv/bin/python -m scripts.download_equity --symbol ^GSPC
    .venv/bin/python -m scripts.download_equity --symbol AAPL --out data/candles/aapl-1d.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
_UA = "Mozilla/5.0 (compatible; crypto-bot/1.0)"


def _slug(symbol: str) -> str:
    return symbol.lstrip("^").lower().replace(".", "-")


def parse_chart_payload(payload: dict[str, Any], symbol: str) -> list[dict[str, str | int]]:
    """Yahoo chart JSON → бары в формате Kline-jsonl.

    Пропускаем бары с null-полями (рыночные дыры / халты). Чистая
    функция (без сети) — тестируется на фикстуре.
    """
    result = payload["chart"]["result"]
    if not result:
        err = payload["chart"].get("error")
        raise SystemExit(f"Yahoo returned no data for {symbol}: {err}")
    block = result[0]
    timestamps: list[int] = block["timestamp"]
    quote = block["indicators"]["quote"][0]

    rows: list[dict[str, str | int]] = []
    for i, ts in enumerate(timestamps):
        o, h, low, c, v = (
            quote["open"][i],
            quote["high"][i],
            quote["low"][i],
            quote["close"][i],
            quote["volume"][i],
        )
        if None in (o, h, low, c):
            continue
        rows.append(
            {
                "open": str(o),
                "high": str(h),
                "low": str(low),
                "close": str(c),
                "volume": str(v if v is not None else 0),
                "time": int(ts) * 1000,
            }
        )
    rows.sort(key=lambda r: r["time"])
    return rows


def fetch_yahoo_daily(symbol: str) -> list[dict[str, str | int]]:
    """Тянет дневную историю символа с Yahoo и парсит её."""
    now = int(time.time())
    qs = urllib.parse.urlencode({"period1": 0, "period2": now, "interval": "1d"})
    url = f"{_CHART_URL.format(sym=urllib.parse.quote(symbol))}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return parse_chart_payload(payload, symbol)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download daily TradFi history from Yahoo")
    parser.add_argument("--symbol", required=True, help="Yahoo ticker, напр. ^GSPC, AAPL, NVDA")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Путь jsonl (default: data/candles/<slug>-1d.jsonl)",
    )
    args = parser.parse_args()

    out = args.out or Path("data/candles") / f"{_slug(args.symbol)}-1d.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = fetch_yahoo_daily(args.symbol)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")

    first = rows[0]["time"] if rows else None
    last = rows[-1]["time"] if rows else None
    print(f"saved {len(rows)} daily bars to {out} ({first} → {last})")


if __name__ == "__main__":
    main()
