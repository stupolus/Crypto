"""Antonacci GEM Dual Momentum (план 44.2) — строгий гейт.

Канон (FIXED, не оптимизируется):
- 3 актива: SPY (US, TR), EFA (intl), AGG (bonds); ^IRX → синт.
  T-bill TR (Antonacci использовал прямые рейты, BIL ETF только
  с 2007 — для 2003-2007 надо ^IRX-прокси).
- 12-мес total-return, ребаланс EOM.
- Если r12(SPY) > r12(T-bill): hold max(SPY,EFA) по r12;
  иначе hold AGG. 100% в одном активе, 1 месяц.

Гейт = плана 43: OOS ann-Sharpe>0.8 ∧ PF>1.3 ∧ t>2 ∧
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

_SYMS = {"SPY": "SPY", "EFA": "EFA", "AGG": "AGG", "GSPC": "%5EGSPC", "IRX": "%5EIRX"}
_LOOKBACK_M = 12
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
    """Последняя торговая дата месяца → (date, close)."""
    out: dict[tuple[int, int], tuple[date, float]] = {}
    last: dict[tuple[int, int], tuple[date, float]] = {}
    for d, c in rows:
        last[(d.year, d.month)] = (d, c)
    for k, v in last.items():
        out[k] = v
    return out


def _bill_tr_series(irx_daily: list[tuple[date, float]]) -> dict[tuple[int, int], float]:
    """Синт. кумулятивный T-bill total-return на EOM из ^IRX
    (13-нед yield, annualized %). monthly_TR = avg_yield/12/100.
    Кумулятивный = ∏(1+m_TR). Возвращает уровень индекса = 1.0
    на первый месяц."""
    # сгруппировать по (year, month)
    by_m: dict[tuple[int, int], list[float]] = {}
    for d, y in irx_daily:
        by_m.setdefault((d.year, d.month), []).append(y)
    out: dict[tuple[int, int], float] = {}
    level = 1.0
    for k in sorted(by_m):
        avg = statistics.fmean(by_m[k])
        m_tr = max(avg, 0.0) / 100.0 / 12.0
        level *= 1.0 + m_tr
        out[k] = level
    return out


def _months_before(key: tuple[int, int], n: int) -> tuple[int, int]:
    y, m = key
    total = y * 12 + (m - 1) - n
    return total // 12, total % 12 + 1


def _r12(eom: dict[tuple[int, int], tuple[date, float]], key: tuple[int, int]) -> float | None:
    prev = _months_before(key, _LOOKBACK_M)
    if key not in eom or prev not in eom:
        return None
    return eom[key][1] / eom[prev][1] - 1.0


def _r12_bill(tr: dict[tuple[int, int], float], key: tuple[int, int]) -> float | None:
    prev = _months_before(key, _LOOKBACK_M)
    if key not in tr or prev not in tr:
        return None
    return tr[key] / tr[prev] - 1.0


def _signals_and_returns(
    spy: dict[tuple[int, int], tuple[date, float]],
    efa: dict[tuple[int, int], tuple[date, float]],
    agg: dict[tuple[int, int], tuple[date, float]],
    bill_tr: dict[tuple[int, int], float],
    cost: float,
) -> list[tuple[date, str, float]]:
    """Применяет правило GEM. Возвращает (release_date, asset, return)."""
    common = sorted(set(spy) & set(efa) & set(agg) & set(bill_tr))
    out: list[tuple[date, str, float]] = []
    prev_asset: str | None = None
    for i in range(len(common) - 1):
        k = common[i]
        kn = common[i + 1]
        r12_spy = _r12(spy, k)
        r12_efa = _r12(efa, k)
        r12_bil = _r12_bill(bill_tr, k)
        if r12_spy is None or r12_efa is None or r12_bil is None:
            continue
        target = ("SPY" if r12_spy > r12_efa else "EFA") if r12_spy > r12_bil else "AGG"
        # Доходность за следующий месяц по target
        chosen = {"SPY": spy, "EFA": efa, "AGG": agg}[target]
        ret = chosen[kn][1] / chosen[k][1] - 1.0
        if prev_asset is not None and prev_asset != target:
            ret -= cost  # round-trip кост при смене актива
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
    print("План 44.2 — Antonacci GEM Dual Momentum, строгий гейт.\n")
    rows = {label: _fetch(label, url) for label, url in _SYMS.items()}
    spy = _eom_prices(rows["SPY"])
    efa = _eom_prices(rows["EFA"])
    agg = _eom_prices(rows["AGG"])
    gspc = _eom_prices(rows["GSPC"])
    bill_tr = _bill_tr_series(rows["IRX"])
    for lab, m in (("SPY", spy), ("EFA", efa), ("AGG", agg)):
        keys = sorted(m)
        print(f"  {lab}: {len(keys)} EOM, окно {m[keys[0]][0]}→{m[keys[-1]][0]}")
    trades = _signals_and_returns(spy, efa, agg, bill_tr, _BASE_COST)
    if len(trades) < 60:
        print("\nМало месяцев. СТОП.")
        return
    # Распределение активов
    counts = {"SPY": 0, "EFA": 0, "AGG": 0}
    for _d, a, _r in trades:
        counts[a] += 1
    print(f"\nАллокация (мес-доли): SPY={counts['SPY']} EFA={counts['EFA']} AGG={counts['AGG']}")
    rs = [r for (_d, _a, r) in trades]
    dates = [d for (d, _a, _r) in trades]
    med = dates[len(dates) // 2]
    oos = [r for (d, _a, r) in trades if d >= med]
    st_full = _stats(rs)
    st_oos = _stats(oos)
    dd = _max_dd(rs)
    # BH(^GSPC) на том же окне
    gspc_keys = sorted(gspc)
    first_k = (trades[0][0].year, trades[0][0].month)
    bh = []
    for i in range(1, len(gspc_keys)):
        k0 = gspc_keys[i - 1]
        k1 = gspc_keys[i]
        if k1 >= first_k:
            bh.append(gspc[k1][1] / gspc[k0][1] - 1.0)
    dd_bh = _max_dd(bh)
    print(
        f"\nFULL: ann-Sharpe={st_full['sharpe_a']:.2f} PF={st_full['pf']:.2f} "
        f"t={st_full['t']:.2f} mean/мес={st_full['mean_m'] * 100:.2f}% MaxDD={dd * 100:.1f}%"
    )
    print(
        f"OOS  (split {med}): ann-Sharpe={st_oos['sharpe_a']:.2f} PF={st_oos['pf']:.2f} "
        f"t={st_oos['t']:.2f} N={int(st_oos['n'])}"
    )
    print(f"BH(^GSPC) MaxDD на том же окне: {dd_bh * 100:.1f}%")
    # WF
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
    # Cost-sweep
    print("\nCost-sweep:")
    sweep_ok = True
    for c in _COSTS:
        rs_c = [r for (_d, _a, r) in _signals_and_returns(spy, efa, agg, bill_tr, c)]
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
        and dd > dd_bh
        and wf_ok >= 3
        and sweep_ok
    )
    print(
        "\nГЕЙТ: "
        + ("ПРОШЁЛ ✓" if gate else "НЕ ПРОШЁЛ ✗")
        + f"   (Sharpe>0.8? {st_oos['sharpe_a'] > 0.8}; PF>1.3? {st_oos['pf'] > 1.3}; "
        f"t>2? {st_oos['t'] > 2.0}; DD<BH? {dd > dd_bh}; WF≥3? {wf_ok >= 3}; "
        f"sweep0.20? {sweep_ok})"
    )


if __name__ == "__main__":
    main()
