"""TSMOM крипто-мажоры (план 36.2) — мировой канон на наших данных.

Moskowitz–Ooi–Pedersen: знак доходности за 365д → лонг/шорт,
ребаланс 30д. Equal-weight 6 мажоров. Предзадано, НЕ скан.
Робаст-гейт: OOS PF>1.3 ∧ Sh>0.8 ∧ t>2 ∧ ≥8 корзин; WF≥3/4;
per-coin ≥4/6; cost-sweep. 90д — справочно (не отбор).
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

_COINS = ["btc-usdt", "eth-usdt", "sol-usdt", "doge-usdt", "xrp-usdt", "bnb-usdt"]
_KL = Path("data/candles")
_DAY = 86_400_000
_HOLD = 30
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


def _month(ms: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(ms / 1000, tz=UTC)
    return d.year, d.month


def _stat(rows: list[tuple[int, float]]) -> tuple[float, float, float, int]:
    by: dict[tuple[int, int], list[float]] = {}
    for ms, r in rows:
        by.setdefault(_month(ms), []).append(r)
    s = [sum(v) / len(v) for _, v in sorted(by.items())]
    if len(s) < 8:
        return (0.0, 0.0, 0.0, len(s))
    n = len(s)
    m = sum(s) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in s) / (n - 1))
    sh = m / sd * math.sqrt(12) if sd > 0 else 0.0
    t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
    pos = sum(x for x in s if x > 0)
    neg = -sum(x for x in s if x < 0)
    pf = float("inf") if neg == 0 else pos / neg
    return (pf, sh, t, n)


def _signal(sym: str, lb: int) -> list[tuple[int, float]]:
    cl = _close(sym)
    if not cl:
        return []
    days = sorted(cl)
    out: list[tuple[int, float]] = []
    i = lb
    while i + _HOLD < len(days):
        d = days[i]
        past = days[i - lb]
        if cl[d] <= 0 or cl[past] <= 0:
            i += _HOLD
            continue
        side = 1 if cl[d] > cl[past] else -1
        fwd = cl[days[i + _HOLD]] / cl[d] - 1.0
        out.append((d, fwd * side))
        i += _HOLD
    return out


def _report(lb: int) -> None:
    print(f"-- лукбэк {lb}д, hold {_HOLD}д --")
    pooled: list[tuple[int, float]] = []
    pcoin: dict[str, list[tuple[int, float]]] = {}
    for sym in _COINS:
        r = _signal(sym, lb)
        if r:
            pcoin[sym] = r
            pooled += r
    if not pooled:
        print("  нет данных")
        return
    pooled.sort()
    psplit = pooled[len(pooled) // 2][0]
    for c in _COSTS:
        oos = [(ms, x - c) for ms, x in pooled if ms >= psplit]
        pf, sh, t, nb = _stat(oos)
        # walk-forward 4 фолда
        step = len(pooled) // 4
        wf = sum(
            1
            for k in range(4)
            if sum(v - c for _, v in pooled[k * step : (k + 1) * step])
            / max(1, len(pooled[k * step : (k + 1) * step]))
            > 0
        )
        # per-coin
        pcok = 0
        for r in pcoin.values():
            r2 = sorted(r)
            sp = r2[len(r2) // 2][0]
            o = [(ms, x - c) for ms, x in r2 if ms >= sp]
            ppf, psh, _pt, pnb = _stat(o)
            if ppf > 1.0 and psh > 0.0 and pnb >= 8:
                pcok += 1
        pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
        gate = pf > 1.3 and sh > 0.8 and t > 2.0 and nb >= 8 and wf >= 3 and pcok >= 4
        print(
            f"  cost {c:.2%} OOS PF={pf_s} Sh={sh:+.2f} t={t:+.2f} мес={nb} "
            f"| WF+{wf}/4 per-coin+{pcok}/{len(pcoin)} "
            f"→ {'РОБАСТ+' if gate else '✗'}"
        )


def main() -> None:
    print("TSMOM крипто-мажоры (план 36.2) — мировой канон, наши данные")
    print("Предзадано (365д/30д). Гейт: PF>1.3 Sh>0.8 t>2 ≥8 WF≥3/4 pc≥4/6.")
    print("=" * 70)
    _report(365)
    _report(90)
    print("=" * 70)
    print("Вердикт по 365д (канон). 90д — справочно, НЕ отбор лучшего.")
    print("Не РОБАСТ+ на всех cost → доказательный конец, перебор стоп.")


if __name__ == "__main__":
    main()
