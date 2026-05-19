"""EIA crude inventory — событийная спекуляция (план 39.3).

Предзаданное правило (НЕ скан, Принцип 6):
- change = stocks[t] − stocks[t−1] (недельные, ex-SPR).
- Ожидание (2 модели, предзадано): сезонная норма (среднее
  change той же ISO-недели по ПРОШЛЫМ годам, расширяющееся
  окно, без look-ahead) ИЛИ 4-нед MA прошлых change.
- Сюрприз s = change − ожидание.
- Торгуем только экстремум: |s| ≥ 70-й перцентиль |s| по
  ПРОШЛЫМ событиям (расширяющийся, без look-ahead).
- Неожиданный РОСТ запасов → SHORT WTI; падение → LONG.
- Вход на закрытии релиз-дня (среда после недели-периода),
  удержание 1 и 3 торговых дня (оба, предзадано).
- Без плеча; round-trip cost-sweep 0.07/0.10/0.15%.

Гейт (строгий, не ослабляется): OOS (split по медиане даты)
PF>1.3 ∧ Sharpe>0.8 ∧ t>2 ∧ ≥30 событий-OOS ∧ ≥8 корзин;
WF ≥3/4; cost-sweep. 4 предзаданных среза (2 гориз × 2 ожид) —
нужен явный устойчивый +, не пограничный. Провал → честный
отрицательный вердикт (валидный итог, план это предзадал).
"""

from __future__ import annotations

import json
import math
import statistics
import time
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

_EIA = Path("data/eia/crude_stocks.jsonl")
_HOLDS = (1, 3)
_COSTS = (0.0007, 0.0010, 0.0015)
_EXTREME_Q = 0.70  # |s| ≥ 70-й перцентиль прошлых |s| (крайние 30%)
_MIN_PRIOR = 60  # минимум прошлых событий до первой сделки (стабильный перцентиль)
_SEASONAL_MIN_YEARS = 5  # минимум прошлых лет для сезонной нормы ISO-week


def _load_eia() -> list[tuple[date, float]]:
    rows: list[tuple[date, float]] = []
    for line in _EIA.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        rows.append((date.fromisoformat(r["period"]), float(r["value"])))
    rows.sort(key=lambda x: x[0])
    return rows


def _wti_daily() -> list[tuple[date, float]]:
    u = (
        "https://query1.finance.yahoo.com/v8/finance/chart/CL=F"
        f"?period1=0&period2={int(time.time())}&interval=1d"
    )
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as fh:
        d = json.load(fh)
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    cl = res["indicators"]["quote"][0]["close"]
    out: list[tuple[date, float]] = []
    for t, c in zip(ts, cl, strict=True):
        if c is not None and c > 0:
            out.append((datetime.fromtimestamp(t, tz=UTC).date(), float(c)))
    out.sort(key=lambda x: x[0])
    return out


def _trade_idx_on_or_after(days: list[date], target: date) -> int | None:
    lo, hi = 0, len(days)
    while lo < hi:
        mid = (lo + hi) // 2
        if days[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(days) else None


def _build_events() -> list[dict[str, object]]:
    """Список событий с предзаданными ожиданиями (без look-ahead)."""
    eia = _load_eia()
    changes: list[tuple[date, float]] = []
    for i in range(1, len(eia)):
        changes.append((eia[i][0], eia[i][1] - eia[i - 1][1]))

    events: list[dict[str, object]] = []
    for i, (per, ch) in enumerate(changes):
        prior = changes[:i]  # строго ДО — без look-ahead
        if len(prior) < _MIN_PRIOR:
            continue
        iso_wk = per.isocalendar()[1]
        same_week = [c for (p, c) in prior if p.isocalendar()[1] == iso_wk]
        prior_years = len({p.year for (p, _c) in prior if p.isocalendar()[1] == iso_wk})
        seasonal = (
            statistics.fmean(same_week)
            if prior_years >= _SEASONAL_MIN_YEARS and same_week
            else None
        )
        ma4 = statistics.fmean([c for (_p, c) in prior[-4:]])
        # релиз: отчёт за неделю-период публикуется ~следующую среду
        release = per + timedelta(days=5)
        events.append(
            {
                "period": per,
                "change": ch,
                "release": release,
                "exp_seasonal": seasonal,
                "exp_ma4": ma4,
                "prior_abs": [abs(c) for (_p, c) in prior],
            }
        )
    return events


def _quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    if not s:
        return float("inf")
    pos = q * (len(s) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _trades(model: str, hold: int, cost: float) -> list[tuple[date, float]]:
    wti = _wti_daily()
    wdays = [d for (d, _c) in wti]
    wpx = dict(wti)
    out: list[tuple[date, float]] = []
    for ev in _build_events():
        exp = ev["exp_seasonal"] if model == "seasonal" else ev["exp_ma4"]
        if exp is None:
            continue
        s = float(ev["change"]) - float(exp)  # type: ignore[arg-type]
        prior_abs = ev["prior_abs"]
        thr = _quantile(prior_abs, _EXTREME_Q)  # type: ignore[arg-type]
        if abs(s) < thr:
            continue
        ei = _trade_idx_on_or_after(wdays, ev["release"])  # type: ignore[arg-type]
        if ei is None or ei + hold >= len(wdays):
            continue
        entry = wpx[wdays[ei]]
        exit_ = wpx[wdays[ei + hold]]
        sign = -1.0 if s > 0 else 1.0  # рост запасов → SHORT
        ret = sign * (exit_ / entry - 1.0) - cost
        out.append((wdays[ei], ret))
    return out


def _stats(rets: list[float]) -> dict[str, float]:
    n = len(rets)
    if n < 2:
        return {"n": n, "pf": 0.0, "sharpe": 0.0, "t": 0.0, "mean": 0.0}
    gains = sum(r for r in rets if r > 0)
    losses = -sum(r for r in rets if r < 0)
    pf = gains / losses if losses > 0 else float("inf")
    mean = statistics.fmean(rets)
    sd = statistics.pstdev(rets)
    sharpe = mean / sd if sd > 0 else 0.0
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    return {"n": float(n), "pf": pf, "sharpe": sharpe, "t": t, "mean": mean}


def _buckets(trades: list[tuple[date, float]]) -> int:
    return len({(d.year, (d.month - 1) // 3) for (d, _r) in trades})


def _eval_slice(model: str, hold: int) -> None:
    base = _trades(model, hold, 0.0010)
    if len(base) < 4:
        print(f"  [{model} h{hold}] сделок {len(base)} — нет статбазы. СТОП-срез.")
        return
    dates = sorted(d for (d, _r) in base)
    med = dates[len(dates) // 2]
    is_ = [r for (d, r) in base if d < med]
    oos = [(d, r) for (d, r) in base if d >= med]
    so = _stats([r for (_d, r) in oos])
    nb = _buckets(oos)
    # walk-forward: 4 последовательных фолда, PF>1 ∧ mean>0 в ≥3/4
    wf_ok = 0
    if base:
        q = max(1, len(base) // 4)
        for k in range(4):
            seg = [r for (_d, r) in base[k * q : (k + 1) * q if k < 3 else len(base)]]
            st = _stats(seg)
            if st["pf"] > 1.0 and st["mean"] > 0:
                wf_ok += 1
    print(f"  [{model} h{hold}] всего={len(base)} IS={len(is_)} OOS={int(so['n'])} корзин-OOS={nb}")
    print(
        f"    OOS: PF={so['pf']:.2f} Sharpe={so['sharpe']:.3f} "
        f"t={so['t']:.2f} mean={so['mean'] * 100:.3f}%  WF={wf_ok}/4"
    )
    for c in _COSTS:
        cs = _stats([r for (_d, r) in _trades(model, hold, c) if r is not None])
        print(f"    cost {c * 100:.2f}%: PF={cs['pf']:.2f} t={cs['t']:.2f}")
    gate = (
        so["pf"] > 1.3
        and so["sharpe"] > 0.8
        and so["t"] > 2.0
        and so["n"] >= 30
        and nb >= 8
        and wf_ok >= 3
    )
    print(f"    ГЕЙТ: {'ПРОШЁЛ' if gate else 'НЕ ПРОШЁЛ'}")


def main() -> None:
    if not _EIA.exists():
        print(f"Нет {_EIA} — сначала scripts.eia_probe (план 39.2). СТОП.")
        return
    print("EIA crude-inventory событие — строгий гейт (план 39.3).")
    print("Предзадано: 2 гориз × 2 ожидания = 4 среза. Нужен явный +.\n")
    for model in ("seasonal", "ma4"):
        for hold in _HOLDS:
            _eval_slice(model, hold)
    print(
        "\nНапоминание: даже + здесь = право на demo (план 39.4), НЕ деньги. "
        "Multiple-testing сессии → арбитр demo."
    )


if __name__ == "__main__":
    main()
