"""Sentiment/позиционирование — контр-крауд + smart-vs-dumb (33.13).

Новый класс данных (не цена/funding/liq/cvd): account
long/short ratio. Метрика Щукина #007. CoinGlass v4:
  global-long-short-account-ratio  (толпа)
  top-long-short-position-ratio    (крупные/«умные»)
~1200д ×6 мажоров (глубокая статбаза).

Предзаданные гипотезы (НЕ скан под PnL):
  H1: крауд-контр — глоб. L/S ratio в крайних 20% монеты →
      контр (толпа максимально лонг → шорт, и наоборот).
  H2: smart-vs-dumb — крайнее расхождение top-position vs
      global-account → следуем за «умными».
Горизонты 1/3д. cost-sweep 0.04/0.07/0.10 НЕ ослабляется.
Гейт: OOS PF>1.3 ∧ Sh>0.8 ∧ t>2 ∧ ≥8нед на ВСЕХ cost +
walk-forward (≥3/4 фолдов +). 8 предзаданных вариантов —
multiple-testing помним (Bonferroni-настрой: нужен явный,
устойчивый, не пограничный +).
"""

from __future__ import annotations

import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path

from parsers.coinglass.backfill import map_symbol
from parsers.coinglass.client import CoinglassClient

_COINS = ["btc-usdt", "eth-usdt", "sol-usdt", "doge-usdt", "xrp-usdt", "bnb-usdt"]
_CG = Path("data/coinglass")
_KL = Path("data/candles")
_DAY = 86_400_000
_Q = 0.20
_HORIZONS = [1, 3]
_COSTS = [0.0004, 0.0007, 0.0010]
_GLSR = "/api/futures/global-long-short-account-ratio/history"
_TOPP = "/api/futures/top-long-short-position-ratio/history"


def _fetch() -> None:
    cg = CoinglassClient()
    if not cg.configured:
        print("CoinGlass ключ не настроен — стоп")
        return
    _CG.mkdir(parents=True, exist_ok=True)
    now = int(time.time() * 1000)
    start = now - 1250 * _DAY
    for sym in _COINS:
        m = map_symbol(sym.upper())
        if m is None:
            continue
        _exch, cgs, _ = m
        for path, tag, key in (
            (_GLSR, "glsr", "global_account_long_short_ratio"),
            (_TOPP, "topp", "top_position_long_short_ratio"),
        ):
            out = _CG / f"{sym}-{tag}-1d.jsonl"
            if out.exists():
                continue
            rows = cg._get(
                path,
                {
                    "exchange": "Binance",
                    "symbol": cgs,
                    "interval": "1d",
                    "start_time": start,
                    "end_time": now,
                    "limit": 4500,
                },
            )
            with open(out, "w") as fh:
                for r in rows:
                    fh.write(json.dumps({"ts": int(r["time"]), "v": float(r[key])}) + "\n")
    cg.close()


def _load(p: Path) -> dict[int, float]:
    out: dict[int, float] = {}
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out[int(r["ts"]) - (int(r["ts"]) % _DAY)] = float(r["v"])
    return out


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


def _quantile(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * len(s)))]


def _week(ms: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(ms / 1000, tz=UTC).isocalendar()
    return d[0], d[1]


def _stats(rows: list[tuple[int, float]]) -> tuple[str, bool]:
    by: dict[tuple[int, int], list[float]] = {}
    for ms, r in rows:
        by.setdefault(_week(ms), []).append(r)
    series = [sum(v) / len(v) for _, v in sorted(by.items())]
    if len(series) < 8:
        return f"нед={len(series)} (<8)", False
    n = len(series)
    m = sum(series) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in series) / (n - 1))
    sh = m / sd * math.sqrt(52) if sd > 0 else 0.0
    t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
    pos = sum(x for x in series if x > 0)
    neg = -sum(x for x in series if x < 0)
    pf = float("inf") if neg == 0 else pos / neg
    ok = pf > 1.3 and sh > 0.8 and t > 2.0 and n >= 8
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    return f"нед={n:3d} PF={pf_s:>4s} Sh={sh:+5.2f} t={t:+5.2f} {'✓' if ok else '✗'}", ok


def _wf(raw: list[tuple[int, float]], cost: float, folds: int = 4) -> tuple[str, int]:
    if len(raw) < folds * 8:
        return "WF:мало", 0
    step = len(raw) // folds
    pos = 0
    for k in range(folds):
        seg = raw[k * step : (k + 1) * step]
        if sum(r - cost for _, r in seg) / len(seg) > 0:
            pos += 1
    return f"WF +{pos}/{folds}", pos


def _eval(name: str, raw: list[tuple[int, float]]) -> None:
    if not raw:
        print(f"  {name}: нет наблюдений")
        return
    raw.sort()
    split = raw[len(raw) // 2][0]
    print(f"  {name}: всего {len(raw)}")
    for c in _COSTS:
        oos = [(ms, r - c) for ms, r in raw if ms >= split]
        s, ok = _stats(oos)
        wf, pos = _wf(raw, c)
        verdict = "РЕАЛЬНЫЙ+" if (ok and pos >= 3) else "✗"
        print(f"    cost {c:.2%} OOS {s} | {wf} → {verdict}")


def main() -> None:
    _fetch()
    close = {s: _close(s) for s in _COINS}
    print("Sentiment контр-крауд + smart-vs-dumb (33.13, новый класс)")
    print(f"Экстремум=крайние {_Q:.0%} (предзадано). cost-sweep НЕ ослаблен.")
    print("Гейт: OOS✓ И WF≥3/4 на всех cost. 8 вариантов (multi-test).")
    print("=" * 66)
    for h in _HORIZONS:
        crowd: list[tuple[int, float]] = []
        smart: list[tuple[int, float]] = []
        trendal: list[tuple[int, float]] = []  # крауд-контр В СТОРОНУ тренда
        for sym in _COINS:
            g = _load(_CG / f"{sym}-glsr-1d.jsonl")
            tp = _load(_CG / f"{sym}-topp-1d.jsonl")
            cl = close[sym]
            if not g or not cl:
                continue
            days = sorted(g)
            gv = [g[d] for d in days]
            hi, lo = _quantile(gv, 1 - _Q), _quantile(gv, _Q)
            diffs = [g[d] - tp[d] for d in days if d in tp]
            if diffs:
                dhi = _quantile(diffs, 1 - _Q)
                dlo = _quantile(diffs, _Q)
            cdays = sorted(cl)
            for d in days:
                fk = d + h * _DAY
                if d not in cl or fk not in cl:
                    continue
                fwd = cl[fk] / cl[d] - 1.0
                # SMA50 строго из ПРОШЛЫХ закрытий (без look-ahead)
                past = [cl[x] for x in cdays if x < d][-50:]
                sma = sum(past) / len(past) if len(past) == 50 else None
                if g[d] >= hi:
                    crowd.append((d, fwd * -1))
                    if sma is not None and cl[d] < sma:  # толпа лонг + даунтренд
                        trendal.append((d, fwd * -1))
                elif g[d] <= lo:
                    crowd.append((d, fwd * +1))
                    if sma is not None and cl[d] > sma:  # толпа шорт + аптренд
                        trendal.append((d, fwd * +1))
                if d in tp and diffs:
                    diff = g[d] - tp[d]
                    if diff >= dhi:  # толпа лонг > умных → шорт
                        smart.append((d, fwd * -1))
                    elif diff <= dlo:
                        smart.append((d, fwd * +1))
        print(f"-- H={h}д --")
        _eval("крауд-контр  ", crowd)
        _eval("крауд+тренд  ", trendal)
        _eval("smart-vs-dumb", smart)
    print("=" * 66)
    print("«РЕАЛЬНЫЙ+» = OOS-гейт И WF≥3/4 на всех cost. Иначе шум.")


if __name__ == "__main__":
    main()
