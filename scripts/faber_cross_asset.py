"""Faber 200SMA — кросс-ассет robustness (план 37.4).

ОДНА зафиксированная стратегия (Faber 2007, те же параметры
что план 37, НЕ подгон) на корзине макро/RWA/акций из юниверса
владельца (Yahoo, глубокая история). Это канонический тест
managed-futures тезиса: трендследование — кросс-ассет феномен
(Moskowitz–Ooi–Pedersen). НЕ перебор «где сработает»: печатаем
ВСЁ, судим по широте/консистентности, не по черри-пику.
Крипта не дублируется (план 36: TSMOM-крипта не прошла).
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

# Yahoo-тикеры инструментов из списка владельца с реальной
# глубокой историей (макро/RWA/акции). Зафиксировано ДО прогона.
_UNIV = {
    "GC=F": "Gold",
    "HG=F": "Copper",
    "CL=F": "WTI Oil",
    "^DJI": "DowJones",
    "JPY=X": "USDJPY",
    "AAPL": "Apple",
    "NVDA": "NVIDIA",
    "TSLA": "Tesla",
    "GOOGL": "Alphabet",
    "META": "Meta",
    "MSTR": "MicroStrategy",
}
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
    return [(int(t), float(c)) for t, c in zip(ts, cl, strict=False) if c is not None]


def _metrics(eq: list[tuple[int, float]]) -> tuple[float, float, float]:
    yrs = (eq[-1][0] - eq[0][0]) / (365.25 * 86400)
    cagr = (eq[-1][1] / eq[0][1]) ** (1 / yrs) - 1 if yrs > 0 and eq[0][1] > 0 else 0.0
    rets = [
        math.log(eq[i][1] / eq[i - 1][1])
        for i in range(1, len(eq))
        if eq[i - 1][1] > 0 and eq[i][1] > 0
    ]
    if len(rets) < 30:
        return (0.0, 0.0, 0.0)
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((x - m) ** 2 for x in rets) / (len(rets) - 1))
    sh = m / sd * math.sqrt(252) if sd > 0 else 0.0
    peak = eq[0][1]
    mdd = 0.0
    for _, v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return (cagr, sh, mdd)


def _run(px: list[tuple[int, float]], faber: bool) -> list[tuple[int, float]]:
    cl = [p[1] for p in px]
    eq = 1.0
    out: list[tuple[int, float]] = [(px[0][0], eq)]
    pos = 0
    for i in range(252, len(px)):
        sig = 1
        if faber:
            sma = sum(cl[i - 200 : i]) / 200
            sig = 1 if cl[i] > sma else 0
        if sig != pos:
            eq *= 1 - _COST
            pos = sig
        if cl[i - 1] > 0:
            eq *= 1 + pos * (cl[i] / cl[i - 1] - 1)
        out.append((px[i][0], eq))
    return out


def main() -> None:
    print("Faber 200SMA — кросс-ассет robustness (план 37.4)")
    print("ОДНА фикс-стратегия (не подгон). Судим ШИРОТУ, не черри-пик.")
    print("=" * 74)
    win = 0
    tot = 0
    for sym, label in _UNIV.items():
        try:
            px = _fetch(sym)
        except Exception as e:
            print(f"{label:13s}: fetch ERR {type(e).__name__}")
            continue
        if len(px) < 600:
            print(f"{label:13s}: мало истории (n={len(px)}) — пропуск")
            continue
        bh = _metrics(_run(px, faber=False))
        fb = _metrics(_run(px, faber=True))
        lo = datetime.fromtimestamp(px[0][0], tz=UTC).year
        # «Лучше» = Faber Sharpe > BH Sharpe И maxDD заметно меньше
        better = fb[1] > bh[1] and fb[2] > bh[2] * 0.7
        tot += 1
        win += 1 if better else 0
        print(
            f"{label:13s}({lo}) BH: CAGR{bh[0] * 100:+5.1f}% Sh{bh[1]:+.2f} "
            f"DD{bh[2] * 100:5.0f}% | Faber: CAGR{fb[0] * 100:+5.1f}% "
            f"Sh{fb[1]:+.2f} DD{fb[2] * 100:5.0f}%  {'TF лучше' if better else '—'}"
        )
    print("=" * 74)
    print(f"Faber улучшил risk-adj у {win}/{tot} инструментов.")
    print("Широко (>половины) → трендследование = кросс-ассет феномен")
    print("(managed-futures тезис подтверждён). Узко → не робастно.")
    print("ЧЕСТНО: единичные акции шумнее индекса; FX/металлы — классика")
    print("TSMOM. Это НЕ деплой — оценка широты edge. Крипта: план 36 (нет).")


if __name__ == "__main__":
    main()
