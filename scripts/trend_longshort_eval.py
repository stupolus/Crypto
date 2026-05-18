"""Тренд long/short vs long-cash — commodity/FX (план 37.5).

Замечание владельца: на товарах/FX (в отличие от акций) канон
managed-futures = long И short по тренду (Moskowitz–Pedersen).
Faber-long-cash шорт-сторону не использует. Проверяем ОДИН
предзаданный вариант: тот же 200SMA-сигнал, но ниже SMA —
SHORT (не кэш). Подмножество: Gold/Copper/Oil/USDJPY.

ЧЕСТНО про нефть-2020: −$37 = артефакт экспирации фьюч-
контракта, не реализуемый перпом/индексом. Бары с ценой ≤0
ИСКЛЮЧАЕМ — иначе бэктест выдаст артефакт за edge (hindsight).
По-декадно: робастность шорт-стороны судим по широте, не по
одному событию.
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

_UNIV = {"GC=F": "Gold", "HG=F": "Copper", "CL=F": "WTI Oil", "JPY=X": "USDJPY"}
_COST = 0.0005


def _fetch(sym: str) -> list[tuple[int, float]]:
    q = urllib.parse.quote(sym)
    u = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}"
        f"?period1=0&period2={int(time.time())}&interval=1d"
    )
    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as fh:
        d = json.load(fh)
    res = d["chart"]["result"][0]
    ts = res["timestamp"]
    cl = res["indicators"]["quote"][0]["close"]
    # ИСКЛЮЧАЕМ бары с ценой ≤0 (нефть-2020 артефакт): не
    # реализуемо перпом, не должно давать фейковый edge.
    return [(int(t), float(c)) for t, c in zip(ts, cl, strict=False) if c is not None and c > 0]


def _run(px: list[tuple[int, float]], mode: str) -> list[tuple[int, float]]:
    cl = [p[1] for p in px]
    eq = 1.0
    out: list[tuple[int, float]] = [(px[0][0], eq)]
    pos = 0
    for i in range(252, len(px)):
        sma = sum(cl[i - 200 : i]) / 200
        up = cl[i] > sma
        if mode == "BH":
            sig = 1
        elif mode == "LongCash":
            sig = 1 if up else 0
        else:  # LongShort
            sig = 1 if up else -1
        if sig != pos:
            eq *= 1 - _COST
            pos = sig
        if cl[i - 1] > 0:
            eq *= 1 + pos * (cl[i] / cl[i - 1] - 1)
        out.append((px[i][0], eq))
    return out


def _metrics(eq: list[tuple[int, float]]) -> tuple[float, float, float]:
    yrs = (eq[-1][0] - eq[0][0]) / (365.25 * 86400)
    cagr = (eq[-1][1] / eq[0][1]) ** (1 / yrs) - 1 if yrs > 0 and eq[0][1] > 0 else 0.0
    r = [
        math.log(eq[i][1] / eq[i - 1][1])
        for i in range(1, len(eq))
        if eq[i - 1][1] > 0 and eq[i][1] > 0
    ]
    if len(r) < 30:
        return (0.0, 0.0, 0.0)
    m = sum(r) / len(r)
    sd = math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1))
    sh = m / sd * math.sqrt(252) if sd > 0 else 0.0
    peak = eq[0][1]
    mdd = 0.0
    for _, v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return (cagr, sh, mdd)


def _decade_pos(eq: list[tuple[int, float]]) -> tuple[int, int]:
    by: dict[int, list[float]] = {}
    for t, v in eq:
        by.setdefault((datetime.fromtimestamp(t, tz=UTC).year // 10) * 10, []).append(v)
    pos = tot = 0
    for seg in by.values():
        if len(seg) > 20:
            tot += 1
            if seg[-1] > seg[0]:
                pos += 1
    return (pos, tot)


def main() -> None:
    print("Тренд long/short vs long-cash — commodity/FX (план 37.5)")
    print("Один предзаданный вариант (short ниже SMA). Бары ≤0 искл.")
    print("=" * 72)
    for sym, label in _UNIV.items():
        try:
            px = _fetch(sym)
        except Exception as e:
            print(f"{label}: ERR {type(e).__name__}")
            continue
        if len(px) < 600:
            print(f"{label}: мало истории")
            continue
        line = f"{label:8s}"
        for mode in ("BH", "LongCash", "LongShort"):
            eq = _run(px, mode)
            c, s, dd = _metrics(eq)
            p, t = _decade_pos(eq)
            line += f" | {mode}: C{c * 100:+5.1f}% Sh{s:+.2f} DD{dd * 100:4.0f}% +{p}/{t}дек"
        print(line)
    print("=" * 72)
    print("Шорт-сторона добавляет ценность ⇔ LongShort устойчиво >")
    print("LongCash по Sharpe И по-декадно НА БОЛЬШИНСТВЕ инструментов.")
    print("ЧЕСТНО: нефть-2020 −$37 ИСКЛЮЧЕНА как нереализуемый артефакт")
    print("— это не «упущенный шорт», а hindsight. Судим систематику.")


if __name__ == "__main__":
    main()
