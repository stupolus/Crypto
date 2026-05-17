"""Дневной позиционный композит S1∧S2 (план 34.2).

S1 крауд-контр: global account L/S ratio в крайних 20% → фейд.
S2 funding-экстремум-контр + liq-подтверждение.
Консенсус: позиция ТОЛЬКО когда S1 и S2 одно направление.
Цель: проверить, поднимает ли диверсификация слабых краёв
значимость честно (t>2) — как у фондов. Предзадано, НЕ скан.

Гейт СТРОГИЙ (не ослабляется): OOS PF>1.3 ∧ Sh>0.8 ∧ t>2 ∧
≥8 нед.корзин ∧ walk-forward ≥3/4, на ВСЕХ cost 0.04/0.07/0.10%.
S1/S2 по отдельности печатаем рядом — видно, дал ли консенсус +.
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
_HORIZONS = [1, 3]
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


def _load_liq(p: Path) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            ts = int(r["ts"])
            out[ts - (ts % _DAY)] = (float(r["long_usd"]), float(r["short_usd"]))
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


def _stats(rows: list[tuple[int, float]]) -> tuple[str, bool]:
    by: dict[tuple[int, int], list[float]] = {}
    for ms, r in rows:
        by.setdefault(_week(ms), []).append(r)
    series = [sum(v) / len(v) for _, v in sorted(by.items())]
    if len(series) < 8:
        return f"нед={len(series)} (<8)", False
    n = len(series)
    m = sum(series) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in series) / (n - 1))
    sh = m / sd * math.sqrt(52) if sd > 0 else 0.0
    t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
    pos = sum(x for x in series if x > 0)
    neg = -sum(x for x in series if x < 0)
    pf = float("inf") if neg == 0 else pos / neg
    ok = pf > 1.3 and sh > 0.8 and t > 2.0 and n >= 8
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    return f"нед={n:3d} PF={pf_s:>4s} Sh={sh:+5.2f} t={t:+5.2f} {'✓' if ok else '✗'}", ok


def _wf(raw: list[tuple[int, float]], cost: float, folds: int = 4) -> tuple[str, int]:
    if len(raw) < folds * 8:
        return "WF:мало", 0
    step = len(raw) // folds
    pos = sum(
        1
        for k in range(folds)
        if sum(r - cost for _, r in raw[k * step : (k + 1) * step])
        / max(1, len(raw[k * step : (k + 1) * step]))
        > 0
    )
    return f"WF+{pos}/{folds}", pos


def _report(name: str, raw: list[tuple[int, float]]) -> None:
    if not raw:
        print(f"  {name}: нет наблюдений")
        return
    raw.sort()
    split = raw[len(raw) // 2][0]
    print(f"  {name}: всего {len(raw)}")
    for c in _COSTS:
        oos = [(ms, r - c) for ms, r in raw if ms >= split]
        s, ok = _stats(oos)
        wf, pos = _wf(raw, c)
        v = "РЕАЛЬНЫЙ+" if (ok and pos >= 3) else "✗"
        print(f"    cost {c:.2%} OOS {s} | {wf} → {v}")


def main() -> None:
    print("Композит S1(крауд)∧S2(funding+liq) — план 34.2")
    print(f"Экстремум крайние {_Q:.0%} (предзадано). Строгий гейт t>2+WF.")
    print("=" * 66)
    for h in _HORIZONS:
        s1: list[tuple[int, float]] = []
        s2: list[tuple[int, float]] = []
        cons: list[tuple[int, float]] = []
        for sym in _COINS:
            g = _load_v(_CG / f"{sym}-glsr-1d.jsonl")
            f = _load_v(_CG / f"{sym}-funding-1d.jsonl")
            liq = _load_liq(_CG / f"{sym}-liq-1d.jsonl")
            cl = _close(sym)
            if not g or not f or not cl:
                continue
            gd = sorted(g)
            ghi, glo = _q([g[d] for d in gd], 1 - _Q), _q([g[d] for d in gd], _Q)
            fd = sorted(f)
            fhi, flo = _q([f[d] for d in fd], 1 - _Q), _q([f[d] for d in fd], _Q)
            for d in gd:
                fk = d + h * _DAY
                if d not in cl or fk not in cl:
                    continue
                fwd = cl[fk] / cl[d] - 1.0
                # S1: крауд-контр
                sig1 = 0
                if g[d] >= ghi:
                    sig1 = -1
                elif g[d] <= glo:
                    sig1 = +1
                # S2: funding-контр + liq-подтверждение
                sig2 = 0
                if d in f:
                    if f[d] >= fhi:
                        sig2 = -1
                    elif f[d] <= flo:
                        sig2 = +1
                    if sig2 != 0:
                        lq = liq.get(d)
                        if lq is None:
                            sig2 = 0
                        else:
                            ln, sh_ = lq
                            if sig2 == -1 and ln <= sh_:
                                sig2 = 0
                            if sig2 == 1 and sh_ <= ln:
                                sig2 = 0
                if sig1 != 0:
                    s1.append((d, fwd * sig1))
                if sig2 != 0:
                    s2.append((d, fwd * sig2))
                if sig1 != 0 and sig1 == sig2:
                    cons.append((d, fwd * sig1))
        print(f"-- H={h}д --")
        _report("S1 крауд      ", s1)
        _report("S2 funding+liq", s2)
        _report("S1∧S2 консенс ", cons)
    print("=" * 66)
    print("Консенсус > S1 и S2 по t/WF → диверсификация работает.")
    print("Ни один не «РЕАЛЬНЫЙ+» на всех cost → честно фиксируем 34.3.")


if __name__ == "__main__":
    main()
