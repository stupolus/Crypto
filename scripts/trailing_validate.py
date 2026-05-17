"""Строгая валидация трейлинг-лида (план 22, добивание).

Три проверки сверх первичного теста:
1. OVERLAP-КОРРЕКТНАЯ значимость: сделки 13 монет агрегируются в
   НЕДЕЛЬНЫЙ портфельный ряд (коррелированные одновременные сделки
   → одно наблюдение/неделю). Sharpe/t считаем на этом ряду —
   честное эффективное N, без раздувания.
2. РОБАСТНОСТЬ K·ATR: sweep K∈{1.5,2.0,2.5,3.0}, печатаем ВСЕ
   (без выбора лучшего — анти-оверфит).
3. Консервативные издержки 0.20% round-trip (альты+проскальзыв.).

Глубже история (48 мес мажоров) подтягивается отдельно — больше
баров = захват медвежьего 2022.
"""

from __future__ import annotations

import glob
import json
import math
import os
import subprocess
import sys
from datetime import UTC, datetime

_COINS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT",
    "DOGE-USDT", "ADA-USDT", "AVAX-USDT", "LINK-USDT", "LTC-USDT",
    "TRX-USDT", "DOT-USDT", "SUI-USDT",
]  # fmt: skip
_OPS = "ops"
_ATR_N = 14
_COST = 0.0020
_KS = [1.5, 2.0, 2.5, 3.0]


def _candles(sym: str) -> list[tuple[int, float, float, float]]:
    p = f"data/candles/{sym.lower()}-4h.jsonl"
    out: list[tuple[int, float, float, float]] = []
    if not os.path.exists(p):
        return out
    with open(p) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            out.append(
                (
                    int(d.get("open_time_ms") or d.get("openTime") or d["time"]),
                    float(d["high"]),
                    float(d["low"]),
                    float(d["close"]),
                )
            )
    out.sort(key=lambda r: r[0])
    return out


def _atr(c: list[tuple[int, float, float, float]], i: int) -> float:
    if i < _ATR_N:
        return 0.0
    s = 0.0
    for j in range(i - _ATR_N + 1, i + 1):
        s += max(
            c[j][1] - c[j][2],
            abs(c[j][1] - c[j - 1][3]),
            abs(c[j][2] - c[j - 1][3]),
        )
    return s / _ATR_N


def _trail_ret(
    c: list[tuple[int, float, float, float]],
    ei: int,
    side: str,
    entry: float,
    hard: float,
    k: float,
) -> float:
    long = side == "BUY"
    trail = k * (_atr(c, ei) or entry * 0.01)
    peak = entry
    stop = hard
    for j in range(ei + 1, len(c)):
        hi, lo = c[j][1], c[j][2]
        if long:
            if lo <= stop:
                return stop / entry - 1.0 - _COST
            if hi > peak:
                peak = hi
                stop = max(stop, peak - trail)
        else:
            if hi >= stop:
                return 1.0 - stop / entry - _COST
            if lo < peak:
                peak = lo
                stop = min(stop, peak + trail)
    last = c[-1][3]
    return ((last / entry - 1.0) if long else (1.0 - last / entry)) - _COST


def _week(ms: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(ms / 1000, tz=UTC).isocalendar()
    return d[0], d[1]


def _portfolio_series(trades: list[tuple[int, float]]) -> list[float]:
    """Сделки (entry_ms, ret) → недельный equal-weight портф. ряд."""
    by_w: dict[tuple[int, int], list[float]] = {}
    for ms, r in trades:
        by_w.setdefault(_week(ms), []).append(r)
    return [sum(v) / len(v) for _, v in sorted(by_w.items())]


def _metrics(series: list[float], tag: str) -> str:
    if len(series) < 8:
        return f"{tag}: недель={len(series)} (мало)"
    n = len(series)
    m = sum(series) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in series) / (n - 1))
    sharpe = m / sd * math.sqrt(52) if sd > 0 else 0.0  # недельный→год
    t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
    p = math.erfc(abs(t) / math.sqrt(2))
    pos = sum(1 for x in series if x > 0)
    eq = 1.0
    for x in series:
        eq *= 1 + x
    pnl_pct = (eq - 1) * 100
    gate = "✓" if (sharpe > 0.8 and t > 2.0 and n >= 30) else "✗"
    return (
        f"{tag}: недель={n:3d} Sharpe={sharpe:+5.2f} t={t:+4.2f} "
        f"p={p:.3f} нед+={pos}/{n} итогPnL={pnl_pct:+7.1f}% {gate}"
    )


def main() -> None:
    # Собираем входы один раз (trend_ema), затем sweep K по ним.
    entries: list[tuple[str, int, int, str, float, float]] = []
    cache: dict[str, list[tuple[int, float, float, float]]] = {}
    for sym in _COINS:
        candle = f"data/candles/{sym.lower()}-4h.jsonl"
        if not os.path.exists(candle):
            continue
        t0 = max(
            (os.path.getmtime(f) for f in glob.glob(f"{_OPS}/backtest-*.json")),
            default=0.0,
        )
        subprocess.run(
            [sys.executable, "-m", "scripts.run_backtest", "--strategy",
             "trend_ema_4h", "--symbol", sym, "--candles", candle,
             "--split-fraction", "0.5"],
            check=True, capture_output=True,
        )  # fmt: skip
        c = _candles(sym)
        cache[sym] = c
        idx = {row[0]: i for i, row in enumerate(c)}
        for tag in ("is", "oos"):
            fs = [f for f in glob.glob(f"{_OPS}/backtest-{tag}-*.json") if os.path.getmtime(f) > t0]
            if not fs:
                continue
            with open(max(fs, key=os.path.getmtime)) as fh:
                trades = json.load(fh)["trades"]
            for tr in trades:
                e = tr["entry"]
                ems = int(e["timestamp_ms"])
                if ems not in idx:
                    continue
                hard = float(tr["exits"][0]["price"]) if tr["exits"] else float(e["price"])
                entries.append((sym, ems, idx[ems], e["side"], float(e["price"]), hard))
    if not entries:
        print("нет входов")
        return
    entries.sort(key=lambda x: x[1])
    split_ms = entries[len(entries) // 2][1]
    print("Строгая валидация трейлинг-лида (overlap-корр., издержки 0.20%)")
    print(f"Входов trend_ema: {len(entries)} | sweep K·ATR, без cherry-pick")
    print("=" * 68)
    for k in _KS:
        timed = [
            (ems, _trail_ret(cache[sym], ei, side, ent, hard, k))
            for sym, ems, ei, side, ent, hard in entries
            if ent > 0
        ]
        is_t = [(ms, r) for ms, r in timed if ms < split_ms]
        oos_t = [(ms, r) for ms, r in timed if ms >= split_ms]
        print(f"K={k}:")
        print(f"  {_metrics(_portfolio_series(is_t), 'IS ')}")
        print(f"  {_metrics(_portfolio_series(oos_t), 'OOS')}")
    print("=" * 68)
    print(
        "Гейт (строгий): Sharpe>0.8 И t>2.0 И ≥30 недель, на ОБОИХ\n"
        "IS/OOS и стабильно по K. Иначе — лид не подтверждён."
    )


if __name__ == "__main__":
    main()
