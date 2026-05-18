"""Контр-крауд: per-coin робастность (план 35.2).

Тот же ЗАФИКСИРОВАННЫЙ сигнал (33.13): account L/S ratio в
крайних 20% монеты → фейд, горизонт 1д. БЕЗ новых параметров —
только дизагрегация по монетам (урок l3: пуловый «+» может
жить на 1–2 монетах = selection bias). cost-sweep НЕ ослаблен.
Робастен ⇔ знак + на ≥4/6 монет без катастроф.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

_COINS = ["btc-usdt", "eth-usdt", "sol-usdt", "doge-usdt", "xrp-usdt", "bnb-usdt"]
_CG = Path("data/coinglass")
_KL = Path("data/candles")
_DAY = 86_400_000
_Q = 0.20
_COSTS = [0.0004, 0.0007, 0.0010]


def _load_v(p: Path) -> dict[int, float]:
    out: dict[int, float] = {}
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            ts = int(r["ts"])
            out[ts - (ts % _DAY)] = float(r["v"])
    return out


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


def _q(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * len(s)))]


def _week(ms: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(ms / 1000, tz=UTC).isocalendar()
    return d[0], d[1]


def _stat(rows: list[tuple[int, float]]) -> tuple[float, float, float, int]:
    by: dict[tuple[int, int], list[float]] = {}
    for ms, r in rows:
        by.setdefault(_week(ms), []).append(r)
    s = [sum(v) / len(v) for _, v in sorted(by.items())]
    if len(s) < 8:
        return (0.0, 0.0, 0.0, len(s))
    n = len(s)
    m = sum(s) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in s) / (n - 1))
    sh = m / sd * math.sqrt(52) if sd > 0 else 0.0
    t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
    pos = sum(x for x in s if x > 0)
    neg = -sum(x for x in s if x < 0)
    pf = float("inf") if neg == 0 else pos / neg
    return (pf, sh, t, n)


def _signal(sym: str) -> list[tuple[int, float]]:
    g = _load_v(_CG / f"{sym}-glsr-1d.jsonl")
    cl = _close(sym)
    if not g or not cl:
        return []
    days = sorted(g)
    gv = [g[d] for d in days]
    hi, lo = _q(gv, 1 - _Q), _q(gv, _Q)
    out: list[tuple[int, float]] = []
    for d in days:
        fk = d + _DAY
        if d not in cl or fk not in cl:
            continue
        fwd = cl[fk] / cl[d] - 1.0
        if g[d] >= hi:
            out.append((d, fwd * -1))
        elif g[d] <= lo:
            out.append((d, fwd * +1))
    out.sort()
    return out


def main() -> None:
    print("Контр-крауд per-coin робастность (план 35.2)")
    print("Сигнал зафиксирован (33.13). cost-sweep НЕ ослаблен.")
    print("Робастен ⇔ знак + (PF>1 ∧ Sh>0) на ≥4/6 на ВСЕХ cost.")
    print("=" * 70)
    pos_all = dict.fromkeys(_COSTS, 0)
    pooled: list[tuple[int, float]] = []
    for sym in _COINS:
        raw = _signal(sym)
        if not raw:
            print(f"{sym:10s}: нет данных")
            continue
        pooled += raw
        split = raw[len(raw) // 2][0]
        line = f"{sym:10s} n={len(raw):4d} |"
        for c in _COSTS:
            oos = [(ms, r - c) for ms, r in raw if ms >= split]
            pf, sh, t, nb = _stat(oos)
            ok = pf > 1.0 and sh > 0.0 and nb >= 8
            if ok:
                pos_all[c] += 1
            pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
            line += f" c{c * 100:.2f}:PF{pf_s}/Sh{sh:+.2f}/t{t:+.1f}{'+' if ok else '-'}"
        print(line)
    print("-" * 70)
    pooled.sort()
    psplit = pooled[len(pooled) // 2][0]
    pl = "ПУЛ       |"
    for c in _COSTS:
        oos = [(ms, r - c) for ms, r in pooled if ms >= psplit]
        pf, sh, t, nb = _stat(oos)
        pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
        pl += f" c{c * 100:.2f}:PF{pf_s}/Sh{sh:+.2f}/t{t:+.1f}/нед{nb}"
    print(pl)
    print("=" * 70)
    worst = min(pos_all.values())
    print(f"Монет с + : {dict((f'{k:.2%}', v) for k, v in pos_all.items())}")
    if worst >= 4:
        print("ВЕРДИКТ: монето-РОБАСТЕН (≥4/6 на всех cost) — статус")
        print("«реальный модест-сигнал» (план 35.3), НЕ selection bias.")
    else:
        print("ВЕРДИКТ: монето-НЕ-робастен (<4/6) — selection-bias")
        print("артефакт как l3, честно закрыть (план 35.3).")


if __name__ == "__main__":
    main()
