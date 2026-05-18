"""Зависимости металлов: золото/серебро/медь ↔ драйверы.

Считает корреляции дневных лог-доходностей (полная выборка +
последние ~3г для стабильности) между:
  металлы: Gold GC=F, Silver SI=F, Copper HG=F
  драйверы: USD-индекс DX-Y.NYB, ставка-прокси ФРС ^IRX
            (13-нед T-bill), 10y-доходность ^TNX, акции ^GSPC,
            материалы-сектор XLB.
Описательно (корреляция ≠ причинность; реальная ставка требует
CPI — используем номинальные прокси, помечаем честно).
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request

_TICK = {
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "COPPER": "HG=F",
    "USD(DXY)": "DX-Y.NYB",
    "FED~(IRX)": "^IRX",
    "10Y(TNX)": "^TNX",
    "SP500": "^GSPC",
    "MATERIALS": "XLB",
}
_YIELDS = {"FED~(IRX)", "10Y(TNX)"}  # уровни ставок → берём дельту, не log-ret


def _fetch(sym: str) -> dict[int, float]:
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
    day = 86_400_000
    return {
        (int(t) * 1000) // day: float(c)
        for t, c in zip(ts, cl, strict=False)
        if c is not None and c > 0
    }


def _series(name: str, raw: dict[int, float]) -> dict[int, float]:
    days = sorted(raw)
    out: dict[int, float] = {}
    is_yield = name in _YIELDS
    for i in range(1, len(days)):
        a, b = raw[days[i - 1]], raw[days[i]]
        out[days[i]] = (b - a) if is_yield else math.log(b / a)
    return out


def _corr(a: dict[int, float], b: dict[int, float], lo: int = 0) -> tuple[float, int]:
    ks = sorted(k for k in (a.keys() & b.keys()) if k >= lo)
    if len(ks) < 30:
        return (0.0, len(ks))
    xa = [a[k] for k in ks]
    xb = [b[k] for k in ks]
    ma, mb = sum(xa) / len(xa), sum(xb) / len(xb)
    da = math.sqrt(sum((x - ma) ** 2 for x in xa))
    db = math.sqrt(sum((x - mb) ** 2 for x in xb))
    if da == 0 or db == 0:
        return (0.0, len(ks))
    return (
        sum((xa[i] - ma) * (xb[i] - mb) for i in range(len(ks))) / (da * db),
        len(ks),
    )


def main() -> None:
    print("Зависимости металлов ↔ драйверы (описательно)")
    print("=" * 66)
    ser: dict[str, dict[int, float]] = {}
    for name, tick in _TICK.items():
        try:
            ser[name] = _series(name, _fetch(tick))
        except Exception as e:
            print(f"{name}: fetch ERR {type(e).__name__}")
    recent = (int(time.time() // 86400)) - 365 * 3  # ~3 года
    metals = [m for m in ("GOLD", "SILVER", "COPPER") if m in ser]

    print("\n[1] Металлы между собой (corr дневных лог-ret):")
    for i, m1 in enumerate(metals):
        for m2 in metals[i + 1 :]:
            c, n = _corr(ser[m1], ser[m2])
            cr, _ = _corr(ser[m1], ser[m2], recent)
            print(f"  {m1:6s}~{m2:6s}: всё={c:+.2f} (n={n})  3г={cr:+.2f}")

    print("\n[2] Каждый металл ↔ драйвер (всё | 3г):")
    drv = [d for d in _TICK if d not in ("GOLD", "SILVER", "COPPER") and d in ser]
    print("  " + " " * 8 + "  ".join(f"{d:>10s}" for d in drv))
    for m in metals:
        cells = []
        for d in drv:
            c, _ = _corr(ser[m], ser[d])
            cr, _ = _corr(ser[m], ser[d], recent)
            cells.append(f"{c:+.2f}|{cr:+.2f}")
        print(f"  {m:6s}  " + "  ".join(f"{x:>10s}" for x in cells))
    print("=" * 66)
    print("Знак для ставок (IRX/TNX) = corr с ИЗМЕНЕНИЕМ ставки.")
    print("ЧЕСТНО: 'реальная ставка' требует CPI — здесь номинальные")
    print("прокси (DXY/IRX/TNX). Корреляция описательна, не edge и не")
    print("причинность. Структурно (контекст, не из этих чисел):")
    print(" • Gold ↔ обратно USD и реальной ставке + safe-haven.")
    print(" • Silver = gold-beta + промышленный спрос (волатильнее).")
    print(" • Copper ('Dr.Copper') = прокси мирового роста ↔ акции/")
    print("   материалы; чувствителен к Китаю/циклу, не к safe-haven.")


if __name__ == "__main__":
    main()
