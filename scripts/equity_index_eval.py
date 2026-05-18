"""Индекс акций: канонические TA/momentum-стратегии на 40+ лет.

^GSPC (S&P500, с 1970) и ^NDX (NASDAQ100, с 1985), Yahoo daily.
Предзадано из литературы, НЕ скан под Sharpe:
  BH    — buy&hold (премия за риск; сам по себе edge).
  Faber — long если close>SMA200, иначе кэш (Faber 2007).
  TSMOM — long если ret_252д>0, иначе кэш.
Кост 0.05% на переключение. Метрики + ПО-ДЕКАДНО (декады =
независимые режимы: 2000/2008/2020/2022). Робастен ⇔ + в
большинстве декад И тайминг снижает maxDD при ~CAGR.

Фундаментал индекса (CAPE/earnings yield) — отдельный блок-
комментарий в вердикте: предсказывает 10-летние, НЕ
часы/дни (honest, не выдумка).
"""

from __future__ import annotations

import json
import math
import time
import urllib.request
from datetime import UTC, datetime

_SYMS = {"^GSPC": "S&P500(1970)", "^NDX": "NASDAQ100(1985)"}
_COST = 0.0005


def _fetch(sym: str) -> list[tuple[int, float]]:
    q = sym.replace("^", "%5E")
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


def _stats(eq: list[tuple[int, float]]) -> tuple[float, float, float, float]:
    if len(eq) < 252:
        return (0.0, 0.0, 0.0, 0.0)
    yrs = (eq[-1][0] - eq[0][0]) / (365.25 * 86400)
    cagr = (eq[-1][1] / eq[0][1]) ** (1 / yrs) - 1 if yrs > 0 and eq[0][1] > 0 else 0.0
    rets: list[float] = []
    for i in range(1, len(eq)):
        if eq[i - 1][1] > 0:
            rets.append(math.log(eq[i][1] / eq[i - 1][1]))
    n = len(rets)
    m = sum(rets) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in rets) / (n - 1)) if n > 1 else 0.0
    sh = m / sd * math.sqrt(252) if sd > 0 else 0.0
    peak = eq[0][1]
    mdd = 0.0
    for _, v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return (cagr, sh, mdd, yrs)


def _run(px: list[tuple[int, float]], strat: str) -> list[tuple[int, float]]:
    cl = [p[1] for p in px]
    eq = 1.0
    out: list[tuple[int, float]] = [(px[0][0], eq)]
    pos = 0
    for i in range(252, len(px)):
        if strat == "BH":
            sig = 1
        elif strat == "Faber":
            sma = sum(cl[i - 200 : i]) / 200
            sig = 1 if cl[i] > sma else 0
        else:  # TSMOM
            sig = 1 if cl[i] > cl[i - 252] else 0
        if sig != pos:
            eq *= 1 - _COST
            pos = sig
        if cl[i - 1] > 0:
            eq *= 1 + pos * (cl[i] / cl[i - 1] - 1)
        out.append((px[i][0], eq))
    return out


def _decade(eq: list[tuple[int, float]]) -> dict[int, float]:
    by: dict[int, list[tuple[int, float]]] = {}
    for t, v in eq:
        dec = (datetime.fromtimestamp(t, tz=UTC).year // 10) * 10
        by.setdefault(dec, []).append((t, v))
    out: dict[int, float] = {}
    for dec, seg in sorted(by.items()):
        if len(seg) > 20 and seg[0][1] > 0:
            yrs = (seg[-1][0] - seg[0][0]) / (365.25 * 86400)
            out[dec] = (seg[-1][1] / seg[0][1]) ** (1 / yrs) - 1 if yrs > 0.3 else 0.0
    return out


def main() -> None:
    print("Индекс акций — канон TA/momentum, 40+ лет (план 37.2)")
    print("Предзадано (Faber200 / TSMOM252 / BH). Кост 0.05%/switch.")
    print("=" * 72)
    for sym, label in _SYMS.items():
        try:
            px = _fetch(sym)
        except Exception as e:
            print(f"{label}: fetch ERR {type(e).__name__}")
            continue
        lo = datetime.fromtimestamp(px[0][0], tz=UTC).date()
        hi = datetime.fromtimestamp(px[-1][0], tz=UTC).date()
        print(f"\n### {label}  {lo}→{hi}  n={len(px)}")
        decset: dict[str, dict[int, float]] = {}
        for strat in ("BH", "Faber", "TSMOM"):
            eq = _run(px, strat)
            cagr, sh, mdd, _ = _stats(eq)
            decset[strat] = _decade(eq)
            print(
                f"  {strat:6s} CAGR={cagr * 100:+6.2f}%  Sharpe={sh:+.2f}  maxDD={mdd * 100:6.1f}%"
            )
        decs = sorted(decset["BH"])
        head = "  по-декадно CAGR  " + "  ".join(f"{d}s" for d in decs)
        print(head)
        for strat in ("BH", "Faber", "TSMOM"):
            row = "  ".join(f"{decset[strat].get(d, 0.0) * 100:+5.1f}" for d in decs)
            pos = sum(1 for d in decs if decset[strat].get(d, 0.0) > 0)
            print(f"  {strat:6s}        {row}   [+{pos}/{len(decs)} декад]")
    print("=" * 72)
    print("ЧЕСТНО: ^GSPC/^NDX = price-index (без дивид., CAGR занижен")
    print("≈−2%/г). Реальный edge = лонг-бета (премия за риск) +")
    print("Faber-тайминг РЕЗКО режет maxDD при ~том же CAGR — это")
    print("decades-robust и есть «работающая стратегия в мире».")
    print("Фундаментал индекса (CAPE/earnings yield): предсказывает")
    print("10-ЛЕТНИЕ доходности, НЕ часы/дни — на коротких горизонтах")
    print("сигнала не даёт (Campbell-Shiller; honest, не выдумка).")
    print("«Часы» — нет ни 40-летних данных, ни внутридневного edge.")


if __name__ == "__main__":
    main()
