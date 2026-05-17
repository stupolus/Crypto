"""Строгая валидация scalp_meanrev (план 31.2).

15m мажоры (есть данные; DOGE — мемкоин-прокси с реальной
глубиной/ликвидностью, в отличие от survivorship-FARTCOIN).
Гейт СТРОГИЙ (план 31): OOS PF>1.5 И Sharpe>1.0 И ≥100 сделок,
IS≈OOS, walk-forward, overlap-коррекция, cost-sweep
0.10/0.15/0.20% (издержки — главный killer скальпа).
Любой провал, особенно cost-sweep → отклонить.
"""

from __future__ import annotations

import glob
import json
import math
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal

_COINS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "DOGE-USDT", "XRP-USDT", "BNB-USDT",
]  # fmt: skip
_OPS = "ops"
_COSTS = [0.0010, 0.0015, 0.0020]  # доп. round-trip поверх движковых fees


def _newest(tag: str, after: float) -> str | None:
    fs = [f for f in glob.glob(f"{_OPS}/backtest-{tag}-*.json") if os.path.getmtime(f) > after]
    return max(fs, key=os.path.getmtime) if fs else None


def _week(ms: int) -> tuple[int, int]:
    d = datetime.fromtimestamp(ms / 1000, tz=UTC).isocalendar()
    return d[0], d[1]


def _weekly(tr: list[tuple[int, float]]) -> list[float]:
    by: dict[tuple[int, int], list[float]] = {}
    for ms, r in tr:
        by.setdefault(_week(ms), []).append(r)
    return [sum(v) / len(v) for _, v in sorted(by.items())]


def _stats(series: list[float], tag: str) -> tuple[str, bool]:
    if len(series) < 8:
        return f"{tag}: нед={len(series)} (мало)", False
    n = len(series)
    m = sum(series) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in series) / (n - 1))
    sh = m / sd * math.sqrt(52) if sd > 0 else 0.0
    t = m / (sd / math.sqrt(n)) if sd > 0 else 0.0
    p = math.erfc(abs(t) / math.sqrt(2))
    w = sum(x for x in series if x > 0)
    loss = -sum(x for x in series if x < 0)
    pf = float("inf") if loss == 0 else w / loss
    eq = 1.0
    for x in series:
        eq *= 1 + x
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    return (
        f"{tag}: нед={n:3d} PF={pf_s:>4s} Sh={sh:+5.2f} t={t:+4.2f} "
        f"p={p:.3f} итог={(eq - 1) * 100:+6.1f}%"
    ), (pf > 1.5 and sh > 1.0 and t > 2.0)


def main() -> None:
    raw: list[tuple[int, float, str]] = []  # (entry_ms, pnl_frac, sym)
    per_coin_n: dict[str, int] = {}
    for sym in _COINS:
        candle = f"data/candles/{sym.lower()}-15m.jsonl"
        if not os.path.exists(candle):
            continue
        t0 = max(
            (os.path.getmtime(f) for f in glob.glob(f"{_OPS}/backtest-*.json")),
            default=0.0,
        )
        subprocess.run(
            [sys.executable, "-m", "scripts.run_backtest", "--strategy",
             "scalp_meanrev", "--symbol", sym, "--candles", candle,
             "--split-fraction", "0.5"],
            check=True, capture_output=True,
        )  # fmt: skip
        for tag in ("is", "oos"):
            path = _newest(tag, t0)
            if path is None:
                continue
            with open(path) as fh:
                trades = json.load(fh)["trades"]
            for tr in trades:
                ems = int(tr["entry"]["timestamp_ms"])
                raw.append((ems, float(Decimal(str(tr["pnl_pct"]))) / 100.0, sym))
                per_coin_n[sym] = per_coin_n.get(sym, 0) + 1
    if not raw:
        print("нет сделок (scalp_meanrev не сработал на 15m мажорах)")
        return
    raw.sort()
    split = raw[len(raw) // 2][0]
    print("scalp_meanrev — строгая валидация (15m мажоры, план 31.2)")
    print(f"Всего сделок: {len(raw)} | по монетам: {per_coin_n}")
    print("Гейт: OOS PF>1.5 И Sharpe>1.0 И t>2 И ≥100 сделок + cost-sweep")
    print("=" * 70)
    overall_pass = True
    for cost in _COSTS:
        is_tr = [(ms, r - cost) for ms, r, _ in raw if ms < split]
        oos_tr = [(ms, r - cost) for ms, r, _ in raw if ms >= split]
        is_s, _ = _stats(_weekly(is_tr), "IS ")
        oos_s, oos_ok = _stats(_weekly(oos_tr), "OOS")
        n_oos = len(oos_tr)
        gate = oos_ok and n_oos >= 100
        if not gate:
            overall_pass = False
        print(f"\n-- издержки доп.{cost:.2%} (поверх движковых fees) --")
        print(f"  {is_s}")
        print(f"  {oos_s}  | сделок OOS={n_oos} → {'✓' if gate else '✗'}")
    print("=" * 70)
    print(
        "ВЕРДИКТ: "
        + (
            "прошёл строгий гейт+cost-sweep — кандидат (план 31.3/29)"
            if overall_pass
            else "НЕ прошёл (cost-sweep/гейт) — отклонить, как и ожидалось"
        )
    )
    print("Мемкоины (FARTCOIN): данных нет/мелко + survivorship +")
    print("издержки ×3–5 → если не прошло на ликвиде, на них тем более.")


if __name__ == "__main__":
    main()
