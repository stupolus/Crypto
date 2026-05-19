"""Keller VAA-G4 Aggressive (план 46.2) — строгий гейт.

Канон (FIXED, не оптимизируется):
- Offensive G4: SPY, EFA, EEM, AGG
- Defensive: LQD, IEF, SHY
- Score 13612W: 12·r1 + 4·r3 + 2·r6 + 1·r12 (monthly r = p/p_lag − 1)
- T=1, B=1: если все 4 offensive > 0 → top-1 offensive;
  иначе → top-1 defensive (по тому же score).
- EOM ребаланс, hold 1 месяц, round-trip cost при смене актива.

Гейт = плана 43/44: OOS ann-Sharpe>0.8 ∧ PF>1.3 ∧ t>2 ∧
MaxDD<BH(^GSPC) ∧ WF≥3/4 ∧ cost-sweep PF>1.0 @ 0.20%.
"""

from __future__ import annotations

import json
import math
import statistics
import time
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

_OFFENSIVE = ("SPY", "EFA", "EEM", "AGG")
_DEFENSIVE = ("LQD", "IEF", "SHY")
_BENCH = ("GSPC",)  # ^GSPC для MaxDD-сравнения
_BASE_COST = 0.0010
_COSTS = (0.0005, 0.0010, 0.0020)
_CACHE = Path("data/yahoo")


def _fetch(label: str, url: str) -> list[tuple[date, float]]:
    _CACHE.mkdir(parents=True, exist_ok=True)
    cache = _CACHE / f"{label}.jsonl"
    if cache.exists() and time.time() - cache.stat().st_mtime < 86_400:
        out: list[tuple[date, float]] = []
        for line in cache.read_text().splitlines():
            r = json.loads(line)
            out.append((date.fromisoformat(r["d"]), float(r["c"])))
        return out
    u = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{url}"
        f"?period1=0&period2={int(time.time())}&interval=1d"
    )
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as fh:
        d = json.load(fh)
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    adj = res["indicators"].get("adjclose") or [{}]
    cl = adj[0].get("adjclose") if adj else None
    if cl is None:
        cl = res["indicators"]["quote"][0]["close"]
    rows: list[tuple[date, float]] = []
    for t, c in zip(ts, cl, strict=True):
        if c is not None and c > 0:
            rows.append((datetime.fromtimestamp(t, tz=UTC).date(), float(c)))
    rows.sort(key=lambda x: x[0])
    with cache.open("w") as fh:
        for d_, c in rows:
            fh.write(json.dumps({"d": d_.isoformat(), "c": c}) + "\n")
    return rows


def _eom_prices(rows: list[tuple[date, float]]) -> dict[tuple[int, int], tuple[date, float]]:
    last: dict[tuple[int, int], tuple[date, float]] = {}
    for d, c in rows:
        last[(d.year, d.month)] = (d, c)
    return last


def _months_before(key: tuple[int, int], n: int) -> tuple[int, int]:
    y, m = key
    total = y * 12 + (m - 1) - n
    return total // 12, total % 12 + 1


def _score_13612w(
    eom: dict[tuple[int, int], tuple[date, float]], key: tuple[int, int]
) -> float | None:
    """13612W = 12·r1 + 4·r3 + 2·r6 + 1·r12. None если нет истории."""
    p0 = eom.get(key)
    if p0 is None:
        return None
    weights = ((1, 12), (3, 4), (6, 2), (12, 1))
    total = 0.0
    for lag, w in weights:
        pl = eom.get(_months_before(key, lag))
        if pl is None:
            return None
        total += w * (p0[1] / pl[1] - 1.0)
    return total


def _signals_and_returns(
    eoms: dict[str, dict[tuple[int, int], tuple[date, float]]], cost: float
) -> list[tuple[date, str, float]]:
    """Применяет VAA-G4 Aggressive (T=1, B=1)."""
    common = sorted(set.intersection(*(set(eoms[a].keys()) for a in eoms)))
    out: list[tuple[date, str, float]] = []
    prev_asset: str | None = None
    for i in range(len(common) - 1):
        k = common[i]
        kn = common[i + 1]
        off_scores = {a: _score_13612w(eoms[a], k) for a in _OFFENSIVE}
        def_scores = {a: _score_13612w(eoms[a], k) for a in _DEFENSIVE}
        if any(s is None for s in off_scores.values()) or any(
            s is None for s in def_scores.values()
        ):
            continue
        all_off_positive = all(s > 0 for s in off_scores.values())  # type: ignore[operator]
        if all_off_positive:
            target = max(_OFFENSIVE, key=lambda a: off_scores[a])  # type: ignore[arg-type, return-value]
        else:
            target = max(_DEFENSIVE, key=lambda a: def_scores[a])  # type: ignore[arg-type, return-value]
        chosen = eoms[target]
        ret = chosen[kn][1] / chosen[k][1] - 1.0
        if prev_asset is not None and prev_asset != target:
            ret -= cost
        out.append((chosen[kn][0], target, ret))
        prev_asset = target
    return out


def _stats(rets: list[float]) -> dict[str, float]:
    n = len(rets)
    if n < 2:
        return {"n": float(n), "pf": 0.0, "sharpe_a": 0.0, "t": 0.0, "mean_m": 0.0}
    gains = sum(r for r in rets if r > 0)
    losses = -sum(r for r in rets if r < 0)
    pf = gains / losses if losses > 0 else float("inf")
    mean = statistics.fmean(rets)
    sd = statistics.pstdev(rets)
    sharpe_a = (mean / sd * math.sqrt(12)) if sd > 0 else 0.0
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    return {"n": float(n), "pf": pf, "sharpe_a": sharpe_a, "t": t, "mean_m": mean}


def _max_dd(rets: list[float]) -> float:
    eq = 1.0
    peak = 1.0
    dd = 0.0
    for r in rets:
        eq *= 1.0 + r
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1.0)
    return dd


def main() -> None:
    print("План 46.2 — Keller VAA-G4 Aggressive, строгий гейт.\n")
    all_syms = (
        ("SPY", "SPY"),
        ("EFA", "EFA"),
        ("EEM", "EEM"),
        ("AGG", "AGG"),
        ("LQD", "LQD"),
        ("IEF", "IEF"),
        ("SHY", "SHY"),
        ("GSPC", "%5EGSPC"),
    )
    rows = {label: _fetch(label, url) for label, url in all_syms}
    eoms = {label: _eom_prices(rows[label]) for label, _ in all_syms}
    for lab in (*_OFFENSIVE, *_DEFENSIVE):
        keys = sorted(eoms[lab])
        print(f"  {lab}: {len(keys)} EOM, окно {eoms[lab][keys[0]][0]}→{eoms[lab][keys[-1]][0]}")
    trades = _signals_and_returns({a: eoms[a] for a in (*_OFFENSIVE, *_DEFENSIVE)}, _BASE_COST)
    if len(trades) < 60:
        print("\nМало месяцев. СТОП.")
        return
    counts: dict[str, int] = {}
    for _d, a, _r in trades:
        counts[a] = counts.get(a, 0) + 1
    print(f"\nАллокация мес-долей: {dict(sorted(counts.items()))}")
    rs = [r for (_d, _a, r) in trades]
    dates = [d for (d, _a, _r) in trades]
    med = dates[len(dates) // 2]
    oos = [r for (d, _a, r) in trades if d >= med]
    st_full = _stats(rs)
    st_oos = _stats(oos)
    dd_p = _max_dd(rs)
    gspc_keys = sorted(eoms["GSPC"])
    first_k = (trades[0][0].year, trades[0][0].month)
    bh = []
    for i in range(1, len(gspc_keys)):
        k0 = gspc_keys[i - 1]
        k1 = gspc_keys[i]
        if k1 >= first_k:
            bh.append(eoms["GSPC"][k1][1] / eoms["GSPC"][k0][1] - 1.0)
    dd_bh = _max_dd(bh)
    print(
        f"\nFULL: ann-Sharpe={st_full['sharpe_a']:.2f} PF={st_full['pf']:.2f} "
        f"t={st_full['t']:.2f} mean/мес={st_full['mean_m'] * 100:.2f}% MaxDD={dd_p * 100:.1f}%"
    )
    print(
        f"OOS  (split {med}): ann-Sharpe={st_oos['sharpe_a']:.2f} PF={st_oos['pf']:.2f} "
        f"t={st_oos['t']:.2f} N={int(st_oos['n'])}"
    )
    print(f"BH(^GSPC) MaxDD на том же окне: {dd_bh * 100:.1f}%")
    q = len(rs) // 4
    wf_ok = 0
    for k in range(4):
        seg = rs[k * q : (k + 1) * q if k < 3 else len(rs)]
        st = _stats(seg)
        ok = st["pf"] > 1.0 and st["mean_m"] > 0
        wf_ok += 1 if ok else 0
        print(
            f"WF[{k + 1}/4]: PF={st['pf']:.2f} mean={st['mean_m'] * 100:.2f}% {'OK' if ok else 'fail'}"
        )
    print("\nCost-sweep:")
    sweep_ok = True
    for c in _COSTS:
        rs_c = [
            r
            for (_d, _a, r) in _signals_and_returns(
                {a: eoms[a] for a in (*_OFFENSIVE, *_DEFENSIVE)}, c
            )
        ]
        st = _stats(rs_c)
        ok = st["pf"] > 1.0
        if c == 0.0020:
            sweep_ok = ok
        print(
            f"  cost {c * 100:.2f}%: PF={st['pf']:.2f} ann-Sharpe={st['sharpe_a']:.2f} "
            f"t={st['t']:.2f}"
        )
    gate = (
        st_oos["sharpe_a"] > 0.8
        and st_oos["pf"] > 1.3
        and st_oos["t"] > 2.0
        and dd_p > dd_bh
        and wf_ok >= 3
        and sweep_ok
    )
    print(
        "\nГЕЙТ: "
        + ("ПРОШЁЛ ✓" if gate else "НЕ ПРОШЁЛ ✗")
        + f"   (Sharpe>0.8? {st_oos['sharpe_a'] > 0.8}; PF>1.3? {st_oos['pf'] > 1.3}; "
        f"t>2? {st_oos['t'] > 2.0}; DD<BH? {dd_p > dd_bh}; WF≥3? {wf_ok >= 3}; "
        f"sweep0.20? {sweep_ok})"
    )


if __name__ == "__main__":
    main()
