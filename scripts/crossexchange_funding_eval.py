"""Кросс-источниковая robustness: funding-extreme на Binance vs Bybit.

ОДИН предзаданный сигнал (план 33.12): funding в крайних 20%
монеты → контр, горизонт 1д, forward по 1d-клайнам. Считаем
ОТДЕЛЬНО по funding-данным Binance и Bybit (CoinGlass), сравни-
ваем знак/PF/WF. Дисциплина: судим КОНСИСТЕНТНОСТЬ источников,
не «где пройдёт» (это robustness, не p-hacking; априор —
33.12 funding WF слаб, ожидаем подтверждение слабости).
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

from parsers.coinglass.backfill import map_symbol
from parsers.coinglass.client import CoinglassClient

_COINS = ["btc-usdt", "eth-usdt", "sol-usdt", "doge-usdt", "xrp-usdt", "bnb-usdt"]
_EXCH = ["Binance", "Bybit"]
_KL = Path("data/candles")
_DAY = 86_400_000
_Q = 0.20
_COSTS = [0.0004, 0.0007, 0.0010]


def _close(sym: str) -> dict[int, float]:
    out: dict[int, float] = {}
    p = _KL / f"{sym}-1d.jsonl"
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            t = int(r.get("time") or r.get("open_time") or r.get("timestamp"))
            out[t - (t % _DAY)] = float(r["close"])
    return out


def _fund(cg: CoinglassClient, exch: str, cgs: str) -> dict[int, float]:
    now = int(time.time() * 1000)
    out: dict[int, float] = {}
    cur = now - 1100 * _DAY
    while cur < now:
        end = min(cur + 900 * _DAY, now)
        try:
            rows = cg.get_funding_history(
                exchange=exch, symbol=cgs, interval="1d",
                start_time_ms=cur, end_time_ms=end,
            )  # fmt: skip
        except Exception:
            return out
        if not rows:
            break
        for ts, v in rows:
            out[int(ts) - (int(ts) % _DAY)] = float(v)
        cur = max(int(rows[-1][0]) + _DAY, cur + _DAY)
        time.sleep(0.3)
    return out


def _eval(raw: list[tuple[int, float]]) -> tuple[float, float, int, int]:
    """-> (PF, Sharpe, n_oos, wf_pos) на недельных корзинах OOS."""
    if not raw:
        return (0.0, 0.0, 0, 0)
    raw.sort()
    split = raw[len(raw) // 2][0]
    oos = [(ms, r) for ms, r in raw if ms >= split]
    import datetime

    by: dict[tuple[int, int], list[float]] = {}
    for ms, r in oos:
        d = datetime.datetime.fromtimestamp(ms / 1000, datetime.UTC).isocalendar()
        by.setdefault((d[0], d[1]), []).append(r)
    s = [sum(v) / len(v) for _, v in sorted(by.items())]
    if len(s) < 8:
        return (0.0, 0.0, len(oos), 0)
    n = len(s)
    m = sum(s) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in s) / (n - 1))
    sh = m / sd * math.sqrt(52) if sd > 0 else 0.0
    pos = sum(x for x in s if x > 0)
    neg = -sum(x for x in s if x < 0)
    pf = float("inf") if neg == 0 else pos / neg
    step = max(1, len(raw) // 4)
    wf = sum(
        1
        for k in range(4)
        if sum(r for _, r in raw[k * step : (k + 1) * step])
        / max(1, len(raw[k * step : (k + 1) * step]))
        > 0
    )
    return (pf, sh, len(oos), wf)


def main() -> None:
    print("Кросс-источник: funding-extreme контр (Binance vs Bybit)")
    print("Один предзаданный сигнал. Судим КОНСИСТЕНТНОСТЬ, не подбор.")
    print("=" * 68)
    cg = CoinglassClient()
    close = {s: _close(s) for s in _COINS}
    try:
        for exch in _EXCH:
            raw: list[tuple[int, float]] = []
            covered = 0
            for sym in _COINS:
                m = map_symbol(sym.upper())
                if m is None:
                    continue
                _e, cgs, _ = m
                fnd = _fund(cg, exch, cgs)
                cl = close[sym]
                if not fnd or not cl:
                    continue
                covered += 1
                days = sorted(fnd)
                fv = sorted(fnd[d] for d in days)
                hi = fv[min(len(fv) - 1, int(0.8 * len(fv)))]
                lo = fv[min(len(fv) - 1, int(0.2 * len(fv)))]
                for d in days:
                    fk = d + _DAY
                    if d not in cl or fk not in cl:
                        continue
                    fwd = cl[fk] / cl[d] - 1.0
                    if fnd[d] >= hi:
                        raw.append((d, fwd * -1))
                    elif fnd[d] <= lo:
                        raw.append((d, fwd * +1))
            for c in _COSTS:
                pf, sh, n, wf = _eval([(ms, r - c) for ms, r in raw])
                pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
                print(
                    f"  {exch:8s} cov={covered}/6 cost {c:.2%}: "
                    f"OOS n={n:4d} PF={pf_s} Sh={sh:+.2f} WF+{wf}/4"
                )
    finally:
        cg.close()
    print("=" * 68)
    print("Консистентны и оба слабы → подтверждение 33.12 (funding не")
    print("edge), источник не артефакт. Резко разойдутся → один из")
    print("источников шумит, сигналу верить нельзя. Не подбор.")


if __name__ == "__main__":
    main()
