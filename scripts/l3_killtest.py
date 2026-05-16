"""Kill-тесты кандидата l3_oi_drop_flat_price (план 23).

l3 «прошёл» гейт на BTC/SOL (НЕ ETH) и был в плюсе на падающем
рынке — единственный кандидат сессии. Перед доверием — те же
проверки, что убили LTC/funding/трейлинг:
1. Реальные издержки (round-trip), 2 уровня.
2. Walk-forward: окно Coinglass на 5 непересек. периодов.
3. Overlap-коррекция: сделки 3 монет → недельный портфельный
   ряд (коррелированные одновременные → одно набл./нед), честный t.
4. Разбор coin-consistency (BTC/ETH/SOL раздельно).

Параметры l3 — из DolfThresholds (источник статья, не подгон).
Вердикт честный: переживёт ВСЁ на ≥2 монетах + портфель значим
→ первый реальный edge; иначе — закрыть.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from core.signals.dolf_setups import DolfContext, detect_l3_oi_drop_flat_price
from parsers.coinglass.backfill import backfill_providers, map_symbol
from parsers.coinglass.client import CoinglassClient

_SYMS = {"BTC-USDT": "BTC-USD", "ETH-USDT": "ETH-USD", "SOL-USDT": "SOL-USD"}
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_H = 5  # горизонт удержания (дн), как в матрице
_COSTS = [0.0012, 0.0020]  # майоры ~0.12%; консерв. 0.20%


class _Fund:
    def __init__(self, s: list[tuple[int, Decimal]]) -> None:
        self._s = sorted(s)

    def get_funding_rate(self, symbol: str, ts: int) -> Decimal | None:
        p: Decimal | None = None
        for t, v in self._s:
            if t > ts:
                break
            p = v
        return p


def _candles(ysym: str) -> list[tuple[int, float, float, float, float]]:
    for _ in range(4):
        try:
            r = httpx.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym}",
                params={"range": "5y", "interval": "1d"},
                headers={"User-Agent": _UA},
                timeout=20,
                follow_redirects=True,
            )
            if r.status_code == 200:
                q = r.json()["chart"]["result"][0]
                ts = q["timestamp"]
                o = q["indicators"]["quote"][0]
                return [
                    (
                        int(ts[i]) * 1000,
                        float(o["high"][i]),
                        float(o["low"][i]),
                        float(o["close"][i]),
                        float(o["volume"][i] or 0),
                    )
                    for i in range(len(ts))
                    if o["close"][i] is not None and o["high"][i] is not None
                ]
            time.sleep(3)
        except httpx.HTTPError:
            time.sleep(3)
    return []


def _l3_trades(sym: str, ysym: str, cg: CoinglassClient, cost: float) -> list[tuple[int, float]]:
    """[(entry_ms, net_ret)] для l3 на дневке, окно Coinglass, с издержками."""
    now = int(time.time() * 1000)
    start = now - int(2.6 * 365 * 24 * 3600 * 1000)
    liq, oi, delta = backfill_providers(sym, "1d", start_time_ms=start, end_time_ms=now, client=cg)
    m = map_symbol(sym)
    if not m:
        return []
    exch, csym, _ = m
    fr = cg.get_funding_history(
        exchange=exch,
        symbol=csym,
        interval="1d",
        start_time_ms=start,
        end_time_ms=now,
        limit=1000,
    )
    lh = cg.get_liquidation_history(
        exchange=exch,
        symbol=csym,
        interval="1d",
        start_time_ms=start,
        end_time_ms=now,
        limit=1000,
    )
    if not lh:
        return []
    tss = [x.timestamp_ms for x in lh]
    lo, hi = min(tss), max(tss)
    fund = _Fund(fr)
    cc = [c for c in _candles(ysym) if lo <= c[0] <= hi]
    out: list[tuple[int, float]] = []
    for i in range(40, len(cc) - _H):
        ctx = DolfContext(
            symbol=sym,
            timestamp_ms=cc[i][0],
            closes=[Decimal(str(c[3])) for c in cc[: i + 1]],
            highs=[Decimal(str(c[1])) for c in cc[: i + 1]],
            lows=[Decimal(str(c[2])) for c in cc[: i + 1]],
            volumes=[Decimal(str(c[4])) for c in cc[: i + 1]],
            liq=liq,
            oi=oi,
            delta=delta,
            funding=fund,
        )
        res = detect_l3_oi_drop_flat_price(ctx)
        if res.triggered:  # l3 — только LONG
            entry = cc[i][3]
            if entry > 0:
                out.append((cc[i][0], cc[i + _H][3] / entry - 1.0 - cost))
    return out


def _stats(rets: list[float], tag: str) -> str:
    if len(rets) < 8:
        return f"{tag}: n={len(rets)} (мало)"
    n = len(rets)
    mn = sum(rets) / n
    sd = math.sqrt(sum((x - mn) ** 2 for x in rets) / (n - 1))
    sh = mn / sd * math.sqrt(252 / _H) if sd > 0 else 0.0
    t = mn / (sd / math.sqrt(n)) if sd > 0 else 0.0
    p = math.erfc(abs(t) / math.sqrt(2))
    w = sum(x for x in rets if x > 0)
    loss = -sum(x for x in rets if x < 0)
    pf = float("inf") if loss == 0 else w / loss
    eq = 1.0
    for x in rets:
        eq *= 1 + x
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    return (
        f"{tag}: n={n:3d} PF={pf_s:>4s} Sh={sh:+5.2f} t={t:+4.2f} "
        f"p={p:.3f} итог={(eq - 1) * 100:+6.1f}%"
    )


def _weekly(tr: list[tuple[int, float]]) -> list[float]:
    by: dict[tuple[int, int], list[float]] = {}
    for ms, r in tr:
        d = datetime.fromtimestamp(ms / 1000, tz=UTC).isocalendar()
        by.setdefault((d[0], d[1]), []).append(r)
    return [sum(v) / len(v) for _, v in sorted(by.items())]


def main() -> None:
    cg = CoinglassClient()
    for cost in _COSTS:
        print(f"\n{'=' * 70}\nИЗДЕРЖКИ {cost:.2%} round-trip\n{'=' * 70}")
        all_tr: list[tuple[int, float]] = []
        for sym, ysym in _SYMS.items():
            tr = _l3_trades(sym, ysym, cg, cost)
            all_tr += tr
            print(f"\n{sym}: {_stats([r for _, r in tr], 'весь период')}")
            if len(tr) >= 20:
                tr.sort()
                t0, t1 = tr[0][0], tr[-1][0]
                sp = max(1, t1 - t0)
                wf = []
                for k in range(5):
                    seg = [r for ms, r in tr if t0 + sp * k // 5 <= ms < t0 + sp * (k + 1) // 5]
                    if len(seg) >= 5:
                        wf.append(sum(seg) / len(seg) > 0)
                print(
                    f"  WF: окон+ {sum(wf)}/{len(wf)}"
                    + (" (устойчив)" if wf and sum(wf) / len(wf) >= 0.7 else " (хрупкий)")
                )
        # overlap-корректный портфель (недельный, 3 монеты)
        print(f"\nПОРТФЕЛЬ (overlap-корр., недельный): {_stats(_weekly(all_tr), '')}")
    cg.close()
    print(
        "\nВердикт: переживёт ВСЁ (издержки 0.20% + WF≥70% + портфель\n"
        "t>2) на ≥2 монетах → первый реальный edge. Иначе — закрыть."
    )


if __name__ == "__main__":
    main()
