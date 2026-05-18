"""Faber demo-runner (план 40.2) — PAPER, без реальных ордеров.

Один прогон/день: индекс-close (Yahoo ^NDX) → Faber 200SMA
сигнал (long/cash, по ВЧЕРАШНЕМУ закрытию — без look-ahead) →
читает публичный BingX-перп close → СИМУЛИРУЕТ позицию/базис →
дозаписывает строку в ops/faber_demo.jsonl. Идемпотентен
(один день — одна строка). НИКАКИХ приватных/торговых
эндпоинтов. Вердикт — не здесь: demo требует ≥4 нед
календаря (план 40.3/40.4), тут только наблюдение+лог.
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

_INDEX = "%5ENDX"  # NASDAQ-100 (Yahoo), глубокая история для SMA200
_PERP = "NCSINASDAQ1002USD-USDT"  # BingX TradFi-перп, публичный quote
_LOG = Path("ops/faber_demo.jsonl")
_SMA = 200


def _yahoo_closes(sym: str) -> list[tuple[int, float]]:
    u = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        f"?period1=0&period2={int(time.time())}&interval=1d"
    )
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as fh:
        d = json.load(fh)
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    cl = res["indicators"]["quote"][0]["close"]
    return [(int(t), float(c)) for t, c in zip(ts, cl, strict=False) if c is not None]


def _bingx_perp_close(symbol: str) -> float | None:
    u = (
        "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
        f"?symbol={symbol}&interval=1d&limit=2"
    )
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as fh:
            d = json.load(fh)
        rows = d.get("data") or []
        if not rows:
            return None
        last = rows[-1]
        return float(last["close"] if isinstance(last, dict) else last[4])
    except Exception:
        return None


def main() -> None:
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    if _LOG.exists():
        for line in _LOG.read_text().splitlines():
            if line.strip() and json.loads(line).get("date") == today:
                print(f"faber_demo: {today} уже записан — идемпотентно, выход")
                return

    idx = _yahoo_closes(_INDEX)
    if len(idx) < _SMA + 2:
        print("faber_demo: мало истории индекса — пропуск")
        return
    closes = [c for _, c in idx]
    # Сигнал по ВЧЕРАШНЕМУ закрытию (idx[-1] — последний завершённый
    # день; SMA по предыдущим 200, без текущего бара).
    sma200 = sum(closes[-_SMA - 1 : -1]) / _SMA
    idx_close = closes[-1]
    signal = "LONG" if idx_close > sma200 else "CASH"

    perp = _bingx_perp_close(_PERP)
    basis_pct = (
        round((perp / idx_close - 1.0) * 100, 4) if perp is not None and idx_close > 0 else None
    )

    row = {
        "date": today,
        "ts": int(time.time()),
        "index_sym": "^NDX",
        "index_close": round(idx_close, 4),
        "sma200": round(sma200, 4),
        "signal": signal,
        "perp_sym": _PERP,
        "perp_close": round(perp, 4) if perp is not None else None,
        "basis_pct": basis_pct,
        "note": "paper-only; verdict требует ≥4нед (план 40.4)",
    }
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LOG.open("a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        f"faber_demo {today}: signal={signal} idx={idx_close:.2f} "
        f"sma200={sma200:.2f} perp={perp} basis={basis_pct}% → лог дозаписан"
    )
    print("Это НЕ вердикт: demo копит ≥4 нед календаря (план 40.3/40.4).")


if __name__ == "__main__":
    main()
