"""Микроструктура SOL и её драйверы (анализ, не стратегия).

Считает по уже собранным данным:
- структура волатильности (дневная ann.vol; внутридневной
  «час-оф-дей» профиль |ret| и объёма);
- автокорреляция доходностей на 5m/15m/30m/1d (mean-revert<0
  / momentum>0) — почему reversion-скальп не сработал;
- день недели;
- драйверы: beta/corr к BTC/ETH; связь дневной доходности с
  funding / ликвидациями / CVD / account L/S (контемпор. и
  лаг-1, лаг = предиктивно);
- поведение после крупных ликвидаций (next-day ret).

Описательно. Корреляция ≠ edge; окно ≈ один макрорежим.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

_KL = Path("data/candles")
_CG = Path("data/coinglass")
_DAY = 86_400_000


def _candles(sym: str, tf: str) -> list[tuple[int, float, float, float, float, float]]:
    p = _KL / f"{sym}-{tf}.jsonl"
    out: list[tuple[int, float, float, float, float, float]] = []
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        t = int(r.get("time") or r.get("open_time") or r.get("timestamp"))
        out.append(
            (
                t,
                float(r["open"]),
                float(r["high"]),
                float(r["low"]),
                float(r["close"]),
                float(r.get("volume", 0.0)),
            )
        )
    out.sort()
    return out


def _ret(cl: list[float]) -> list[float]:
    return [math.log(cl[i] / cl[i - 1]) for i in range(1, len(cl)) if cl[i] > 0 and cl[i - 1] > 0]


def _ac(x: list[float], lag: int) -> float:
    n = len(x)
    if n <= lag + 2:
        return 0.0
    m = sum(x) / n
    den = sum((v - m) ** 2 for v in x)
    if den == 0:
        return 0.0
    num = sum((x[i] - m) * (x[i - lag] - m) for i in range(lag, n))
    return num / den


def _corr(a: list[float], b: list[float]) -> float:
    n = min(len(a), len(b))
    if n < 8:
        return 0.0
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((x - mb) ** 2 for x in b))
    if da == 0 or db == 0:
        return 0.0
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (da * db)


def _load_v(p: Path) -> dict[int, float]:
    out: dict[int, float] = {}
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            ts = int(r["ts"])
            out[ts - (ts % _DAY)] = float(r["v"])
    return out


def _load_liq(p: Path) -> dict[int, tuple[float, float]]:
    out: dict[int, tuple[float, float]] = {}
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            ts = int(r["ts"])
            out[ts - (ts % _DAY)] = (float(r["long_usd"]), float(r["short_usd"]))
    return out


def main() -> None:
    print("SOL микроструктура и драйверы (описательно, не стратегия)")
    print("=" * 68)

    d1 = _candles("sol-usdt", "1d")
    closes1d = [c[4] for c in d1]
    r1d = _ret(closes1d)
    if r1d:
        n = len(r1d)
        m = sum(r1d) / n
        sd = math.sqrt(sum((x - m) ** 2 for x in r1d) / (n - 1))
        lo = datetime.fromtimestamp(d1[0][0] / 1000, tz=UTC).date()
        hi = datetime.fromtimestamp(d1[-1][0] / 1000, tz=UTC).date()
        print(f"\n[1] ВОЛАТИЛЬНОСТЬ (1d, {lo}→{hi}, n={n})")
        print(f"  ср.дн.лог-ret={m * 100:+.3f}%  дн.vol={sd * 100:.2f}%")
        print(f"  ann.vol≈{sd * math.sqrt(365) * 100:.0f}%  (крипта высоковол.)")

    print("\n[2] АВТОКОРР ДОХОДНОСТЕЙ (lag1: <0 mean-revert, >0 momentum)")
    for tf in ("5m", "15m", "30m", "1d"):
        c = _candles("sol-usdt", tf)
        rr = _ret([x[4] for x in c])
        if len(rr) > 50:
            a1, a2, a3 = _ac(rr, 1), _ac(rr, 2), _ac(rr, 3)
            kind = "mean-rev" if a1 < -0.02 else "momentum" if a1 > 0.02 else "~шум"
            print(f"  {tf:>3s} n={len(rr):6d} ac1={a1:+.3f} ac2={a2:+.3f} "
                  f"ac3={a3:+.3f} → {kind}")  # fmt: skip

    print("\n[3] ВНУТРИДНЕВНОЙ ПРОФИЛЬ (5m, час UTC: |ret| и объём)")
    c5 = _candles("sol-usdt", "5m")
    byh_r: dict[int, list[float]] = {}
    byh_v: dict[int, list[float]] = {}
    for i in range(1, len(c5)):
        if c5[i][4] <= 0 or c5[i - 1][4] <= 0:
            continue
        h = datetime.fromtimestamp(c5[i][0] / 1000, tz=UTC).hour
        byh_r.setdefault(h, []).append(abs(math.log(c5[i][4] / c5[i - 1][4])))
        byh_v.setdefault(h, []).append(c5[i][5])
    if byh_r:
        gv = sum(sum(v) / len(v) for v in byh_v.values()) / len(byh_v)
        ranked = sorted(byh_r, key=lambda h: sum(byh_r[h]) / len(byh_r[h]), reverse=True)
        print("  топ-5 волатильных часов UTC (|ret|ср, отн.объём):")
        for h in ranked[:5]:
            ar = sum(byh_r[h]) / len(byh_r[h]) * 100
            av = (sum(byh_v[h]) / len(byh_v[h])) / gv if gv else 0
            print(f"    {h:02d}:00  |ret|={ar:.3f}%  объём×{av:.2f}")
        print(f"  тише всего: {ranked[-1]:02d}:00 / {ranked[-2]:02d}:00 UTC "
              "(совпадает с азиат. ночью/низкой ликвидн.)")  # fmt: skip

    print("\n[4] ДЕНЬ НЕДЕЛИ (1d, ср.лог-ret)")
    byd: dict[int, list[float]] = {}
    for i in range(1, len(d1)):
        if d1[i][4] <= 0 or d1[i - 1][4] <= 0:
            continue
        wd = datetime.fromtimestamp(d1[i][0] / 1000, tz=UTC).weekday()
        byd.setdefault(wd, []).append(math.log(d1[i][4] / d1[i - 1][4]))
    nm = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    if byd:
        print(
            "  " + "  ".join(f"{nm[k]}{sum(byd[k]) / len(byd[k]) * 100:+.2f}%" for k in sorted(byd))
        )

    print("\n[5] ДРАЙВЕРЫ — corr дневной SOL-ret c BTC/ETH (beta-риск)")
    b1 = {c[0] - (c[0] % _DAY): c[4] for c in _candles("btc-usdt", "1d")}
    e1 = {c[0] - (c[0] % _DAY): c[4] for c in _candles("eth-usdt", "1d")}
    s1 = {c[0] - (c[0] % _DAY): c[4] for c in d1}
    days = sorted(set(s1) & set(b1) & set(e1))
    sret = [math.log(s1[days[i]] / s1[days[i - 1]]) for i in range(1, len(days))]
    bret = [math.log(b1[days[i]] / b1[days[i - 1]]) for i in range(1, len(days))]
    eret = [math.log(e1[days[i]] / e1[days[i - 1]]) for i in range(1, len(days))]
    cb, ce = _corr(sret, bret), _corr(sret, eret)
    vb = sum((x - sum(bret) / len(bret)) ** 2 for x in bret) / len(bret)
    beta = (
        sum(
            (sret[i] - sum(sret) / len(sret)) * (bret[i] - sum(bret) / len(bret))
            for i in range(len(sret))
        )
        / len(sret)
        / vb
        if vb
        else 0.0
    )
    print(f"  corr(SOL,BTC)={cb:+.2f}  corr(SOL,ETH)={ce:+.2f}  beta_BTC≈{beta:.2f}")
    print("  → SOL в первом приближении = высокобета-BTC (общий риск-фактор)")

    print("\n[6] ДРАЙВЕРЫ — лаг-1 (предиктивно): след.SOL-ret vs метрика")
    fnd = _load_v(_CG / "sol-usdt-funding-1d.jsonl")
    cvd = _load_v(_CG / "sol-usdt-cvd-1d.jsonl")
    glsr = _load_v(_CG / "sol-usdt-glsr-1d.jsonl")
    liq = _load_liq(_CG / "sol-usdt-liq-1d.jsonl")

    def _metric(name: str, d: int) -> float | None:
        if name == "funding":
            return fnd.get(d)
        if name == "CVDΔ":
            return cvd.get(d, 0.0) - cvd.get(d - _DAY, 0.0) if d - _DAY in cvd else None
        if name == "acctL/S":
            return glsr.get(d)
        if name == "liqdisbal":
            if d in liq and (liq[d][0] + liq[d][1]) > 0:
                return (liq[d][0] - liq[d][1]) / (liq[d][0] + liq[d][1])
            return None
        return None

    for nmv in ("funding", "CVDΔ", "acctL/S", "liqdisbal"):
        xs: list[float] = []
        ys: list[float] = []
        for i in range(1, len(days)):
            v = _metric(nmv, days[i - 1])
            if v is None:
                continue
            xs.append(float(v))
            ys.append(math.log(s1[days[i]] / s1[days[i - 1]]))
        if len(xs) >= 30:
            print(f"  {nmv:>10s}: corr(метрика_t, ret_t+1)={_corr(xs, ys):+.3f}  (n={len(xs)})")

    print("\n[7] ПОСЛЕ КРУПНЫХ ЛИКВИДАЦИЙ (top-20% дни) — ср. след.SOL-ret")
    if liq:
        ld = sorted(d for d in liq if d in s1 and d + _DAY in s1)
        longliq = sorted(ld, key=lambda d: liq[d][0])[-max(1, len(ld) // 5) :]
        shortliq = sorted(ld, key=lambda d: liq[d][1])[-max(1, len(ld) // 5) :]

        def _avgnext(ds: list[int]) -> float:
            v = [math.log(s1[d + _DAY] / s1[d]) for d in ds if s1[d] > 0]
            return sum(v) / len(v) * 100 if v else 0.0

        print(f"  после big LONG-liq:  {_avgnext(longliq):+.2f}%  (лонги вымыло)")
        print(f"  после big SHORT-liq: {_avgnext(shortliq):+.2f}%  (шорты вымыло)")
    print("=" * 68)
    print("Вывод печатается отдельным резюме (см. ответ ассистента).")


if __name__ == "__main__":
    main()
