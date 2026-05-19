"""Faber 2007 GTAA-портфель (план 43.2) — строгий гейт.

5 активов FIXED (^GSPC, ^NDX, GC=F, CL=F, IEF), SMA=200,
ежемесячный ребаланс на EOM, equal-weight ON / cash OFF —
канон Faber 2007, БЕЗ оптимизации параметров.

Без look-ahead: сигнал по close[EOM_t], исполнение по тому же
close[EOM_t] (стандарт для monthly Faber). Кост на turnover.

Гейт: OOS ann-Sharpe>0.8, PF>1.3, MaxDD<BH(^GSPC), t>2 ∧
WF≥3/4 ∧ per-asset ≥3/5 PF>1 на OOS ∧ cost-sweep PF>1.0 @ 0.20%.
Один портфель, фиксированная универсалия — без multiple-testing.
"""

from __future__ import annotations

import json
import math
import statistics
import time
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

_SYMS = {"GSPC": "%5EGSPC", "NDX": "%5ENDX", "GC": "GC%3DF", "CL": "CL%3DF", "IEF": "IEF"}
_SMA_N = 200
_COSTS = (0.0005, 0.0010, 0.0020)
_BASE_COST = 0.0010
_CACHE = Path("data/yahoo")


def _fetch(sym_label: str, url_sym: str) -> list[tuple[date, float]]:
    """Yahoo daily close с кешем на сутки (idempotent)."""
    _CACHE.mkdir(parents=True, exist_ok=True)
    cache = _CACHE / f"{sym_label}.jsonl"
    if cache.exists() and time.time() - cache.stat().st_mtime < 86_400:
        out: list[tuple[date, float]] = []
        for line in cache.read_text().splitlines():
            r = json.loads(line)
            out.append((date.fromisoformat(r["d"]), float(r["c"])))
        return out
    u = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{url_sym}"
        f"?period1=0&period2={int(time.time())}&interval=1d"
    )
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as fh:
        d = json.load(fh)
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    # adjclose = total-return (учитывает дивиденды/сплиты для ETF). Для
    # ценовых индексов (^GSPC/^NDX) и фьючерсов (GC=F/CL=F) равно close.
    # Для IEF добавляет купоны → честный bond-total-return.
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


def _eom_with_sma(rows: list[tuple[date, float]]) -> list[tuple[date, float, float]]:
    """EOM-дни с SMA200 на этот же день. (date, close_eom, sma200)."""
    if len(rows) < _SMA_N + 1:
        return []
    out: list[tuple[date, float, float]] = []
    closes = [c for (_d, c) in rows]
    # SMA200 на индекс i = среднее closes[i-199..i] (inclusive)
    last_key: tuple[int, int] | None = None
    for i in range(_SMA_N - 1, len(rows)):
        d, c = rows[i]
        key = (d.year, d.month)
        # последняя итерация месяца определяется тем, что следующая дата уже в другом месяце
        is_last = i == len(rows) - 1 or (rows[i + 1][0].year, rows[i + 1][0].month) != key
        if is_last and key != last_key:
            sma = sum(closes[i - _SMA_N + 1 : i + 1]) / _SMA_N
            out.append((d, c, sma))
            last_key = key
    return out


def _portfolio_returns(
    eoms: dict[str, list[tuple[date, float, float]]], cost: float
) -> list[tuple[date, float]]:
    """Месячные доходности портфеля. Сигнал по close[EOM], ребаланс по
    тому же close. Доходность = сумма w_i · ret_i − cost · turnover."""
    # Map: asset → {month_key: (date, close, sma)}
    by_month: dict[str, dict[tuple[int, int], tuple[date, float, float]]] = {
        a: {(d.year, d.month): (d, c, s) for (d, c, s) in v} for a, v in eoms.items()
    }
    # Универсальный месячный календарь — пересечение
    common = set.intersection(*(set(by_month[a].keys()) for a in by_month))
    months = sorted(common)
    out: list[tuple[date, float]] = []
    prev_w: dict[str, float] = dict.fromkeys(by_month, 0.0)
    n_assets = len(by_month)
    for i in range(len(months) - 1):
        m, m_next = months[i], months[i + 1]
        # Сигналы и веса на месяц m → m_next
        signals = {a: by_month[a][m][1] > by_month[a][m][2] for a in by_month}
        on = [a for a in by_month if signals[a]]
        w = {a: (1.0 / n_assets if signals[a] else 0.0) for a in by_month}
        turnover = sum(abs(w[a] - prev_w[a]) for a in by_month)
        # Доходность за месяц m → m_next по каждому активу
        ret = 0.0
        for a in on:
            c_now = by_month[a][m][1]
            c_next = by_month[a][m_next][1]
            ret += w[a] * (c_next / c_now - 1.0)
        ret -= cost * turnover
        out.append((by_month[on[0] if on else next(iter(by_month))][m_next][0], ret))
        prev_w = w
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


def _bh_gspc(eoms_gspc: list[tuple[date, float, float]]) -> list[tuple[date, float]]:
    out: list[tuple[date, float]] = []
    for i in range(1, len(eoms_gspc)):
        d, c, _ = eoms_gspc[i]
        out.append((d, c / eoms_gspc[i - 1][1] - 1.0))
    return out


def _per_asset_oos(
    eoms: dict[str, list[tuple[date, float, float]]], med: date
) -> dict[str, dict[str, float]]:
    res: dict[str, dict[str, float]] = {}
    for a, lst in eoms.items():
        # Faber per-asset: ON → ret в следующем месяце, OFF → 0
        rets: list[tuple[date, float]] = []
        for i in range(len(lst) - 1):
            _d, c, s = lst[i]
            if c > s:
                d2, c2, _ = lst[i + 1]
                rets.append((d2, c2 / c - 1.0 - _BASE_COST))
            else:
                rets.append((lst[i + 1][0], 0.0))
        oos = [r for (d, r) in rets if d >= med]
        res[a] = _stats(oos)
    return res


def main() -> None:
    print("План 43.2 — Faber 2007 GTAA-портфель, строгий гейт.\n")
    rows = {label: _fetch(label, url) for label, url in _SYMS.items()}
    eoms = {label: _eom_with_sma(v) for label, v in rows.items()}
    for a, v in eoms.items():
        print(f"  {a}: EOM-точек={len(v)}, окно {v[0][0]}→{v[-1][0]}")
    base = _portfolio_returns(eoms, _BASE_COST)
    if len(base) < 60:
        print("\nМало данных для строгого OOS. СТОП.")
        return
    dates = [d for (d, _r) in base]
    med = dates[len(dates) // 2]
    rs = [r for (_d, r) in base]
    oos = [r for (d, r) in base if d >= med]
    st_full = _stats(rs)
    st_oos = _stats(oos)
    dd_p = _max_dd(rs)
    bh = _bh_gspc(eoms["GSPC"])
    # подрезка BH к общему окну
    bh_aligned = [r for (d, r) in bh if d >= base[0][0]]
    dd_bh = _max_dd(bh_aligned)
    print(
        f"\nПортфель (cost={_BASE_COST * 100:.2f}%): месяцев={int(st_full['n'])}, "
        f"первый={base[0][0]} последний={base[-1][0]}"
    )
    print(
        f"  FULL: ann-Sharpe={st_full['sharpe_a']:.2f} PF={st_full['pf']:.2f} "
        f"t={st_full['t']:.2f} mean/мес={st_full['mean_m'] * 100:.2f}% MaxDD={dd_p * 100:.1f}%"
    )
    print(
        f"  OOS  (split {med}): ann-Sharpe={st_oos['sharpe_a']:.2f} "
        f"PF={st_oos['pf']:.2f} t={st_oos['t']:.2f} N={int(st_oos['n'])}"
    )
    print(f"  BH(^GSPC) на том же окне: MaxDD={dd_bh * 100:.1f}%")
    # WF: 4 последовательных фолда
    q = len(base) // 4
    wf_ok = 0
    for k in range(4):
        seg = rs[k * q : (k + 1) * q if k < 3 else len(rs)]
        st = _stats(seg)
        ok = st["pf"] > 1.0 and st["mean_m"] > 0
        wf_ok += 1 if ok else 0
        print(
            f"  WF[{k + 1}/4]: PF={st['pf']:.2f} mean/мес={st['mean_m'] * 100:.2f}% "
            f"{'OK' if ok else 'fail'}"
        )
    # Per-asset OOS
    per = _per_asset_oos(eoms, med)
    print("\nPer-asset Faber на OOS:")
    pa_ok = 0
    for a, st in per.items():
        ok = st["pf"] > 1.0
        pa_ok += 1 if ok else 0
        print(
            f"  {a:5s} PF={st['pf']:.2f} ann-Sharpe={st['sharpe_a']:.2f} {'OK' if ok else 'fail'}"
        )
    # Cost-sweep
    print("\nCost-sweep (портфель целиком):")
    sweep_ok = True
    for c in _COSTS:
        rets_c = [r for (_d, r) in _portfolio_returns(eoms, c)]
        st = _stats(rets_c)
        ok = st["pf"] > 1.0
        sweep_ok = sweep_ok and (ok if c == 0.0020 else True)
        print(
            f"  cost {c * 100:.2f}%: PF={st['pf']:.2f} ann-Sharpe={st['sharpe_a']:.2f} "
            f"t={st['t']:.2f}"
        )
    # Финальный вердикт по предзаданному гейту
    gate = (
        st_oos["sharpe_a"] > 0.8
        and st_oos["pf"] > 1.3
        and st_oos["t"] > 2.0
        and dd_p > dd_bh  # MaxDD ближе к нулю = больше как число (оба отрицательные)
        and wf_ok >= 3
        and pa_ok >= 3
        and sweep_ok
    )
    print(
        "\nГЕЙТ: "
        + ("ПРОШЁЛ ✓" if gate else "НЕ ПРОШЁЛ ✗")
        + f"   (OOS Sharpe>{0.8}? {st_oos['sharpe_a'] > 0.8}; "
        f"PF>{1.3}? {st_oos['pf'] > 1.3}; t>2? {st_oos['t'] > 2.0}; "
        f"DD<BH? {dd_p > dd_bh}; WF≥3? {wf_ok >= 3}; "
        f"per-asset≥3? {pa_ok >= 3}; sweep0.20? {sweep_ok})"
    )


if __name__ == "__main__":
    main()
