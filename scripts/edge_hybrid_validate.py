"""Валидация edge_hybrid — промежуточный гейт (план 33).

Промежуточный (НЕ деплой): OOS PF>1.3 ∧ Sh>0.8 ∧ t>1.5 ∧
≥60 сделок ∧ ≥8 недельных корзин; cost-sweep НЕ ослаблен.
Цель — дорасти до целевого: PF>1.5 ∧ Sh>1.0 ∧ t>2 ∧ ≥100.
Печатаем фактическое число недельных корзин и разрыв до цели.
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
_COSTS = [0.0010, 0.0015, 0.0020]
# Таймфрейм из argv (по умолч. 15m): data/candles/<sym>-<tf>.jsonl
_TF = sys.argv[1] if len(sys.argv) > 1 else "15m"


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


def _stats(series: list[float], tag: str) -> tuple[str, bool, bool]:
    """-> (текст, прошёл_промежуточный, прошёл_целевой)."""
    if len(series) < 8:
        return f"{tag}: нед={len(series)} (<8, статбазы нет)", False, False
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
    interim = pf > 1.3 and sh > 0.8 and t > 1.5
    target = pf > 1.5 and sh > 1.0 and t > 2.0
    return (
        (
            f"{tag}: нед={n:3d} PF={pf_s:>4s} Sh={sh:+5.2f} t={t:+4.2f} "
            f"p={p:.3f} итог={(eq - 1) * 100:+6.1f}%"
        ),
        interim,
        target,
    )


def main() -> None:
    raw: list[tuple[int, float, str]] = []
    per_coin_n: dict[str, int] = {}
    for sym in _COINS:
        candle = f"data/candles/{sym.lower()}-{_TF}.jsonl"
        if not os.path.exists(candle):
            continue
        t0 = max(
            (os.path.getmtime(f) for f in glob.glob(f"{_OPS}/backtest-*.json")),
            default=0.0,
        )
        subprocess.run(
            [sys.executable, "-m", "scripts.run_backtest", "--strategy",
             "edge_hybrid", "--symbol", sym, "--candles", candle,
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
        print("нет сделок (edge_hybrid не сработал на 15m мажорах)")
        return
    raw.sort()
    split = raw[len(raw) // 2][0]
    print(f"edge_hybrid — промежуточный гейт ({_TF} мажоры, план 33)")
    print(f"Всего сделок: {len(raw)} | по монетам: {per_coin_n}")
    print("Промеж.: PF>1.3 Sh>0.8 t>1.5 ≥60 ≥8нед | Цель: PF>1.5 Sh>1.0 t>2 ≥100")
    print("=" * 70)
    interim_pass = True
    for cost in _COSTS:
        is_tr = [(ms, r - cost) for ms, r, _ in raw if ms < split]
        oos_tr = [(ms, r - cost) for ms, r, _ in raw if ms >= split]
        oos_w = _weekly(oos_tr)
        is_s, _, _ = _stats(_weekly(is_tr), "IS ")
        oos_s, oos_interim, oos_target = _stats(oos_w, "OOS")
        n_oos = len(oos_tr)
        gate_i = oos_interim and n_oos >= 60 and len(oos_w) >= 8
        gate_t = oos_target and n_oos >= 100 and len(oos_w) >= 8
        if not gate_i:
            interim_pass = False
        print(f"\n-- издержки доп.{cost:.2%} (cost-sweep НЕ ослаблен) --")
        print(f"  {is_s}")
        print(
            f"  {oos_s}  | OOS сделок={n_oos} нед.корзин={len(oos_w)} "
            f"→ промеж.{'✓' if gate_i else '✗'} цель{'✓' if gate_t else '✗'}"
        )
    print("=" * 70)
    print(
        "ВЕРДИКТ (промеж.): "
        + (
            "ПРОШЁЛ — право продолжать roadmap (НЕ edge, НЕ деньги)"
            if interim_pass
            else "НЕ прошёл промежуточный — следующий шаг roadmap (план 33)"
        )
    )
    print("Напоминание: live закрыт CLAUDE.md; это бэктест-веха, не сигнал.")


if __name__ == "__main__":
    main()
