"""Funding-extreme контр-сигнал + liq-подтверждение (план 33.12).

Принцип №3 / Щукин #007: экстремальный funding = перекос
позиционирования (перегруженная сторона платит). Контр-вход;
опц. подтверждение доминированием ликвидаций перегруженной
стороны (вымывание началось). НЕ ценовой паттерн.

Данные (глубокие, ранее не тестированные так):
  data/coinglass/<sym>-funding-1d.jsonl  ~999д ×6 мажоров
  data/coinglass/<sym>-liq-1d.jsonl
  data/candles/<sym>-1d.jsonl            (forward-доходность)

ВСЁ предзадано (квантиль экстремума, горизонт) — НЕ скан под
PnL. 4 предзаданных варианта (2 горизонта × {с liq, без}) —
multiple-testing учтён (4 — мало, помним). cost-sweep НЕ
ослабляется. Гейт: OOS PF>1.3 ∧ Sharpe>0.8 ∧ t>2 ∧ ≥8
нед.корзин, на всех cost-уровнях.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

_COINS = ["btc-usdt", "eth-usdt", "sol-usdt", "doge-usdt", "xrp-usdt", "bnb-usdt"]
_CG = Path("data/coinglass")
_KL = Path("data/candles")
_Q = 0.20  # экстремум = крайние 20% funding монеты (предзадано)
_HORIZONS = [1, 3]  # дней держим (документированный распад funding)
_COSTS = [0.0004, 0.0007, 0.0010]  # round-trip, daily-оборот (консерв.)


def _load_ts_val(p: Path) -> dict[int, float]:
    out: dict[int, float] = {}
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out[int(r["ts"])] = float(r["v"])
    return out


def _load_liq(p: Path) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out[int(r["ts"])] = (float(r["long_usd"]), float(r["short_usd"]))
    return out


def _load_daily_close(sym: str) -> dict[int, float]:
    out: dict[int, float] = {}
    p = _KL / f"{sym}-1d.jsonl"
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        t = int(r.get("time") or r.get("open_time") or r.get("timestamp"))
        day = t - (t % 86_400_000)
        out[day] = float(r["close"])
    return out


def _quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * len(s)))]


def _week(ms: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(ms / 1000, tz=UTC).isocalendar()
    return d[0], d[1]


def _stats(rows: list[tuple[int, float]], tag: str) -> str:
    by: dict[tuple[int, int], list[float]] = {}
    for ms, r in rows:
        by.setdefault(_week(ms), []).append(r)
    series = [sum(v) / len(v) for _, v in sorted(by.items())]
    if len(series) < 8:
        return f"{tag}: нед={len(series)} (<8 нет статбазы)"
    n = len(series)
    m = sum(series) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in series) / (n - 1))
    sh = m / sd * math.sqrt(52) if sd > 0 else 0.0
    t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
    p = math.erfc(abs(t) / math.sqrt(2))
    pos = sum(x for x in series if x > 0)
    neg = -sum(x for x in series if x < 0)
    pf = float("inf") if neg == 0 else pos / neg
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    gate = "✓" if (pf > 1.3 and sh > 0.8 and t > 2.0 and n >= 8) else "✗"
    return (
        f"{tag}: нед={n:3d} PF={pf_s:>4s} Sh={sh:+5.2f} t={t:+5.2f} "
        f"p={p:.3f} ret={m * n * 100:+6.1f}% {gate}"
    )


def _variant(h: int, use_liq: bool) -> None:
    raw: list[tuple[int, float]] = []
    for sym in _COINS:
        fund = _load_ts_val(_CG / f"{sym}-funding-1d.jsonl")
        liq = _load_liq(_CG / f"{sym}-liq-1d.jsonl")
        close = _load_daily_close(sym)
        if not fund or not close:
            continue
        days = sorted(fund)
        fvals = [fund[d] for d in days]
        hi = _quantile(fvals, 1 - _Q)
        lo = _quantile(fvals, _Q)
        for d in days:
            f = fund[d]
            side = 0
            if f >= hi:
                side = -1  # лонги перегружены → контр-шорт
            elif f <= lo:
                side = +1
            if side == 0:
                continue
            if use_liq:
                lq = liq.get(d)
                if lq is None:
                    continue
                long_liq, short_liq = lq
                # перегруженная сторона должна вымываться
                if side == -1 and long_liq <= short_liq:
                    continue
                if side == 1 and short_liq <= long_liq:
                    continue
            dkey = d - (d % 86_400_000)
            future = d + h * 86_400_000
            fkey = future - (future % 86_400_000)
            if dkey not in close or fkey not in close:
                continue
            ret = (close[fkey] / close[dkey] - 1.0) * side
            raw.append((d, ret))
    if not raw:
        print(f"  H={h} liq={use_liq}: нет наблюдений")
        return
    raw.sort()
    split = raw[len(raw) // 2][0]
    tag = f"H={h}д liq={'да' if use_liq else 'нет'}"
    print(f"  -- {tag}: всего {len(raw)} --")
    for c in _COSTS:
        oos = [(ms, r - c) for ms, r in raw if ms >= split]
        print(f"    cost {c:.2%} {_stats(oos, 'OOS')}")


def main() -> None:
    print("Funding-extreme контр + liq (план 33.12, deep CoinGlass 1d)")
    print(f"Экстремум=крайние {_Q:.0%} funding монеты (предзадано). 6 мажоров.")
    print("Гейт: OOS PF>1.3 ∧ Sh>0.8 ∧ t>2 ∧ ≥8нед на ВСЕХ cost.")
    print("=" * 66)
    for h in _HORIZONS:
        for use_liq in (False, True):
            _variant(h, use_liq)
    print("=" * 66)
    print("Все ✗ → funding-edge на наших данных нет, фиксируем честно.")
    print("Хоть один ✓ на всех cost+OOS → реальный кандидат (план 29).")


if __name__ == "__main__":
    main()
