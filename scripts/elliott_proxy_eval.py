"""Объективный прокси волн Эллиота: ZigZag + Фибо-0.618 откат (план 22).

Реальный Эллиот не определён объективно (субъективная разметка =
оверфит). Берём САМЫЙ ЩЕДРЫЙ автоматизируемый суррогат:
- ZigZag-пивоты (свинг ≥ pct) → направление импульса;
- вход в сторону импульса на откате к Фибо-0.618 предыдущей волны;
- стоп за 1.0-уровнем волны, TP к 1.618-расширению.
Это верхняя оценка «волнового» подхода. Гейт тот же + итогPnL.
БЕЗ cherry-pick: все 13 монет, портфельно, overlap-корр.
"""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime

_COINS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT",
    "DOGE-USDT", "ADA-USDT", "AVAX-USDT", "LINK-USDT", "LTC-USDT",
    "TRX-USDT", "DOT-USDT", "SUI-USDT",
]  # fmt: skip
_ZZ_PCT = 0.05  # порог свинга ZigZag (5% — каноничное, не подгон)
_FIB_ENTRY = 0.618
_FIB_TP = 1.618
_COST = 0.002


def _closes_ts(sym: str) -> list[tuple[int, float]]:
    p = f"data/candles/{sym.lower()}-4h.jsonl"
    out: list[tuple[int, float]] = []
    if not os.path.exists(p):
        return out
    with open(p) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            ts = int(d.get("open_time_ms") or d.get("openTime") or d["time"])
            out.append((ts, float(d["close"])))
    out.sort(key=lambda r: r[0])
    return out


def _zigzag(prices: list[float]) -> list[int]:
    """Пивоты: разворот при откате ≥ _ZZ_PCT от текущего экстремума.

    Старт-направление задаётся первым значимым ходом от prices[0].
    """
    if len(prices) < 3:
        return []
    piv = [0]
    ext_i = 0
    direction = 0  # 0 пока не определено, 1 вверх, -1 вниз
    for i in range(1, len(prices)):
        if prices[ext_i] <= 0:
            ext_i = i
            continue
        chg = prices[i] / prices[ext_i] - 1.0
        if direction == 0:
            if chg >= _ZZ_PCT:
                direction, ext_i = 1, i
            elif chg <= -_ZZ_PCT:
                direction, ext_i = -1, i
            continue
        if direction == 1:
            if prices[i] > prices[ext_i]:
                ext_i = i
            elif prices[i] / prices[ext_i] - 1.0 <= -_ZZ_PCT:
                piv.append(ext_i)
                direction, ext_i = -1, i
        else:
            if prices[i] < prices[ext_i]:
                ext_i = i
            elif prices[i] / prices[ext_i] - 1.0 >= _ZZ_PCT:
                piv.append(ext_i)
                direction, ext_i = 1, i
    piv.append(ext_i)
    return piv


def _trades(ts: list[int], pr: list[float]) -> list[tuple[int, float]]:
    """Вход в сторону импульса волны на откате 0.618; анти-look-ahead:
    используем только завершённые пивоты."""
    piv = _zigzag(pr)
    out: list[tuple[int, float]] = []
    for k in range(2, len(piv) - 1):
        a, b = piv[k - 1], piv[k]  # последняя завершённая волна a→b
        pa, pb = pr[a], pr[b]
        if pa == pb:
            continue
        up = pb > pa  # импульс вверх
        fib_entry = pb - (pb - pa) * _FIB_ENTRY  # откат 0.618
        # ищем после b бар, коснувшийся отката, входим в сторону импульса
        for j in range(b + 1, min(len(pr) - 1, piv[k + 1] + 1)):
            touched = (up and pr[j] <= fib_entry) or (not up and pr[j] >= fib_entry)
            if not touched:
                continue
            entry = pr[j]
            stop = pa
            ext = abs(pb - pa) * (_FIB_TP - 1.0)  # 1.618-расширение волны
            tp = pb + ext if up else pb - ext
            # форвард до stop/tp
            for m in range(j + 1, len(pr)):
                hit_tp = (up and pr[m] >= tp) or (not up and pr[m] <= tp)
                hit_sl = (up and pr[m] <= stop) or (not up and pr[m] >= stop)
                if hit_tp:
                    r = abs(tp / entry - 1.0) - _COST
                    out.append((ts[m], r))
                    break
                if hit_sl:
                    r = -abs(stop / entry - 1.0) - _COST
                    out.append((ts[m], r))
                    break
            break
    return out


def _week(ms: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(ms / 1000, tz=UTC).isocalendar()
    return d[0], d[1]


def _weekly(tr: list[tuple[int, float]]) -> list[float]:
    by: dict[tuple[int, int], list[float]] = {}
    for ms, r in tr:
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
    gate = "✓" if (pf > 1.3 and sharpe > 0.8 and t > 2.0 and n >= 30) else "✗"
    return (
        f"{tag}: недель={n:3d} PF={pf_s:>4s} Sharpe={sharpe:+5.2f} "
        f"t={t:+4.2f} p={p:.3f} итогPnL={(eq - 1) * 100:+7.1f}% {gate}"
    )


def main() -> None:
    all_tr: list[tuple[int, float]] = []
    for sym in _COINS:
        ser = _closes_ts(sym)
        if len(ser) < 200:
            continue
        ts = [t for t, _ in ser]
        pr = [c for _, c in ser]
        all_tr += _trades(ts, pr)
    print("Эллиот-прокси (ZigZag 5% + Фибо-0.618 вход, 1.618 TP), 13 монет")
    print("Самый щедрый объективный суррогат; реальный Эллиот субъективнее.")
    print("=" * 70)
    if not all_tr:
        print("нет сделок")
        return
    all_tr.sort(key=lambda r: r[0])
    split = all_tr[len(all_tr) // 2][0]
    print(f"Всего сделок: {len(all_tr)}")
    print(_m(_weekly([t for t in all_tr if t[0] < split]), "IS "))
    print(_m(_weekly([t for t in all_tr if t[0] >= split]), "OOS"))
    print("\nГейт: OOS PF>1.3 И Sharpe>0.8 И t>2 И ≥30 недель.")


if __name__ == "__main__":
    main()
