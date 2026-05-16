"""Парный стат-арб (коинтеграция), маркет-нейтрал (план 30).

Единственная не протестированная и доступная категория из
GitHub-обзора. Маркет-нейтрал (лонг A − шорт B) убирает
крипто-бету. БЕЗ cherry-pick: все пары из 13 монет, среднее.

Логика: спред = logA − β·logB (β rolling, только прошлое).
z = (спред − mean)/std на rolling-окне. |z|>2 → контр-вход,
z→0 → выход, |z|>3.5 → стоп. Каноничные пороги, не подгон.

Гейт: OOS PF>1.3 И Sharpe>0.8 И ≥30 + t>2, портфельно
(недельная агрегация, overlap-корректно), IS/OOS + walk-forward.
"""

from __future__ import annotations

import itertools
import json
import math
import os
from datetime import UTC, datetime

_COINS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT",
    "DOGE-USDT", "ADA-USDT", "AVAX-USDT", "LINK-USDT", "LTC-USDT",
    "TRX-USDT", "DOT-USDT", "SUI-USDT",
]  # fmt: skip
_BETA_W = 90  # баров (4h) для β-регрессии
_Z_W = 90  # баров для z-score
_ENTRY_Z = 2.0
_STOP_Z = 3.5
_COST = 0.002  # round-trip обе ноги


def _closes(sym: str) -> dict[int, float]:
    p = f"data/candles/{sym.lower()}-4h.jsonl"
    out: dict[int, float] = {}
    if not os.path.exists(p):
        return out
    with open(p) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            ts = int(d.get("open_time_ms") or d.get("openTime") or d["time"])
            out[ts] = float(d["close"])
    return out


def _ols_beta(xs: list[float], ys: list[float]) -> float:
    """β из y = α + β·x (log-цены). Только переданное окно (прошлое)."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    var = sum((x - mx) ** 2 for x in xs)
    return cov / var if var > 0 else 0.0


def _pair_trades(a: list[float], b: list[float], ts: list[int]) -> list[tuple[int, float]]:
    """(exit_ts, доход сделки) для пары. Анти-look-ahead: β,z по прошлому."""
    la = [math.log(x) for x in a]
    lb = [math.log(x) for x in b]
    trades: list[tuple[int, float]] = []
    pos = 0  # +1: лонг спреда (лонг A, шорт B); -1: наоборот
    entry_spread = 0.0
    start = max(_BETA_W, _Z_W)
    for i in range(start, len(a) - 1):
        beta = _ols_beta(lb[i - _BETA_W : i], la[i - _BETA_W : i])
        spr = [la[j] - beta * lb[j] for j in range(i - _Z_W, i)]
        m = sum(spr) / len(spr)
        sd = math.sqrt(sum((s - m) ** 2 for s in spr) / (len(spr) - 1))
        if sd <= 0:
            continue
        cur = la[i] - beta * lb[i]
        z = (cur - m) / sd
        if pos == 0:
            if z > _ENTRY_Z:
                pos, entry_spread = -1, cur  # спред высок → шорт спреда
            elif z < -_ENTRY_Z:
                pos, entry_spread = 1, cur
        else:
            exit_now = (pos == 1 and z >= 0) or (pos == -1 and z <= 0)
            stop = abs(z) > _STOP_Z
            if exit_now or stop:
                # доход спред-сделки ≈ pos·(Δspread) минус издержки
                pnl = pos * (cur - entry_spread) - _COST
                trades.append((ts[i], pnl))
                pos = 0
    return trades


def _week(ms: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(ms / 1000, tz=UTC).isocalendar()
    return d[0], d[1]


def _weekly(trades: list[tuple[int, float]]) -> list[float]:
    by: dict[tuple[int, int], list[float]] = {}
    for ms, r in trades:
        by.setdefault(_week(ms), []).append(r)
    return [sum(v) / len(v) for _, v in sorted(by.items())]


def _m(series: list[float], tag: str) -> str:
    if len(series) < 8:
        return f"{tag}: недель={len(series)} (мало)"
    n = len(series)
    mean = sum(series) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in series) / (n - 1))
    sharpe = mean / sd * math.sqrt(52) if sd > 0 else 0.0
    t = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    p = math.erfc(abs(t) / math.sqrt(2))
    w = sum(x for x in series if x > 0)
    loss = -sum(x for x in series if x < 0)
    pf = float("inf") if loss == 0 else w / loss
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    eq = 1.0
    for x in series:
        eq *= 1 + x
    pnl_pct = (eq - 1) * 100
    gate = "✓" if (pf > 1.3 and sharpe > 0.8 and t > 2.0 and n >= 30) else "✗"
    return (
        f"{tag}: недель={n:3d} PF={pf_s:>4s} Sharpe={sharpe:+5.2f} "
        f"t={t:+4.2f} p={p:.3f} итогPnL={pnl_pct:+7.1f}% {gate}"
    )


def main() -> None:
    series = {s: _closes(s) for s in _COINS}
    series = {s: v for s, v in series.items() if len(v) > max(_BETA_W, _Z_W) + 60}
    syms = sorted(series)
    print(f"Парный стат-арб: {len(syms)} монет, {len(syms) * (len(syms) - 1) // 2} пар")
    print("Без cherry-pick, маркет-нейтрал, издержки 0.20%, overlap-корр.")
    print("=" * 66)
    all_tr: list[tuple[int, float]] = []
    for x, y in itertools.combinations(syms, 2):
        common = sorted(set(series[x]) & set(series[y]))
        if len(common) < max(_BETA_W, _Z_W) + 60:
            continue
        a = [series[x][t] for t in common]
        b = [series[y][t] for t in common]
        all_tr += _pair_trades(a, b, common)
    if not all_tr:
        print("нет сделок")
        return
    all_tr.sort(key=lambda r: r[0])
    split = all_tr[len(all_tr) // 2][0]
    is_w = _weekly([t for t in all_tr if t[0] < split])
    oos_w = _weekly([t for t in all_tr if t[0] >= split])
    print(f"Всего парных сделок: {len(all_tr)}")
    print(_m(is_w, "IS "))
    print(_m(oos_w, "OOS"))
    # walk-forward 5 окон по времени
    print("-" * 66)
    t0, t1 = all_tr[0][0], all_tr[-1][0]
    span = max(1, t1 - t0)
    pos_w = 0
    tot = 0
    for wnd in range(5):
        seg = [r for ms, r in all_tr if t0 + span * wnd // 5 <= ms < t0 + span * (wnd + 1) // 5]
        if len(seg) < 8:
            print(f"  окно {wnd}: n={len(seg)} (мало)")
            continue
        mm = sum(seg) / len(seg)
        ss = math.sqrt(sum((x - mm) ** 2 for x in seg) / (len(seg) - 1))
        sh = mm / ss * math.sqrt(len(seg)) if ss > 0 else 0.0
        tot += 1
        if mm > 0:
            pos_w += 1
        print(f"  окно {wnd}: n={len(seg):4d} mean={mm * 100:+.3f}% t≈{sh:+4.2f}")
    if tot:
        print(f"Окон mean>0: {pos_w}/{tot}")
    print("\nГейт: OOS PF>1.3 И Sharpe>0.8 И t>2 И ≥30 + WF-устойчивость.")


if __name__ == "__main__":
    main()
