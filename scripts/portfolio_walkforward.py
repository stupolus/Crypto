"""Walk-forward равновесного крипто-портфеля (план 22, решающая проверка).

Лид: trend_ema_4h-портфель OOS-стабилен (Sharpe>0.8) но PF<1.3.
Вопрос: это настоящий устойчивый край или его тащат 1-2 удачных
окна (как было с LTC)? Проверяем скользящими непересекающимися
окнами по ВСЕМ сделкам 13 монет за 24 мес.

Без подгонки: окна фиксированы, параметры стратегии не трогаем.
Решение: лид настоящий, если >=70% окон PF>1 и Sharpe>0; хрупкий,
если держится на 1-2 окнах.

Запуск: .venv/bin/python -m scripts.portfolio_walkforward
"""

from __future__ import annotations

import glob
import json
import math
import os
import subprocess
import sys
from decimal import Decimal

_COINS = [
    "BTC-USDT",
    "ETH-USDT",
    "SOL-USDT",
    "BNB-USDT",
    "XRP-USDT",
    "DOGE-USDT",
    "ADA-USDT",
    "AVAX-USDT",
    "LINK-USDT",
    "LTC-USDT",
    "TRX-USDT",
    "DOT-USDT",
    "SUI-USDT",
]
_OPS = "ops"
_DAY_MS = 24 * 3600 * 1000
_WINDOW_DAYS = 120
_YEAR_MS = 365 * _DAY_MS


def _newest(tag: str, after: float) -> str | None:
    fs = [f for f in glob.glob(f"{_OPS}/backtest-{tag}-*.json") if os.path.getmtime(f) > after]
    return max(fs, key=os.path.getmtime) if fs else None


def _window_metrics(
    rows: list[tuple[int, float, float]], n_sleeves: int
) -> tuple[int, float, float, float]:
    """(n, PF, Sharpe, ret%) для одного окна; вес 1/N, общая эквити."""
    if not rows or n_sleeves == 0:
        return 0, 0.0, 0.0, 0.0
    rows.sort(key=lambda r: r[0])
    w = 1.0 / n_sleeves
    equity = 1.0
    rets: list[float] = []
    wins = 0.0
    losses = 0.0
    for _, pnl, base in rows:
        r = w * (pnl / base)
        equity *= 1.0 + r
        rets.append(r)
        if pnl > 0:
            wins += pnl
        else:
            losses += -pnl
    pf = float("inf") if losses == 0 else wins / losses
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / len(rets) if len(rets) > 1 else 0.0
    std = math.sqrt(var)
    sharpe = mean / std * math.sqrt(len(rets)) if std > 0 else 0.0
    return len(rows), pf, sharpe, (equity - 1.0) * 100.0


def main() -> None:
    all_rows: list[tuple[int, float, float]] = []
    sleeves: set[str] = set()
    for sym in _COINS:
        candle = f"data/candles/{sym.lower()}-4h.jsonl"
        if not os.path.exists(candle):
            continue
        t0 = max(
            (os.path.getmtime(f) for f in glob.glob(f"{_OPS}/backtest-*.json")),
            default=0.0,
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.run_backtest",
                "--strategy",
                "trend_ema_4h",
                "--symbol",
                sym,
                "--candles",
                candle,
                "--split-fraction",
                "0.5",
            ],
            check=True,
            capture_output=True,
        )
        for tag in ("is", "oos"):
            path = _newest(tag, t0)
            if path is None:
                continue
            with open(path) as fh:
                d = json.load(fh)
            base = float(d.get("config", {}).get("initial_equity", 1000.0))
            for tr in d["trades"]:
                if not tr["exits"]:
                    continue
                exit_ms = int(tr["exits"][-1]["timestamp_ms"])
                all_rows.append((exit_ms, float(Decimal(str(tr["pnl"]))), base))
                sleeves.add(sym)
    if not all_rows:
        print("нет сделок")
        return
    all_rows.sort(key=lambda r: r[0])
    t_min, t_max = all_rows[0][0], all_rows[-1][0]
    win_ms = _WINDOW_DAYS * _DAY_MS
    n_sleeves = len(sleeves)
    print(
        f"Walk-forward портфеля trend_ema_4h: окно {_WINDOW_DAYS}д, "
        f"{n_sleeves} монет, всего сделок {len(all_rows)}"
    )
    print("окно | даты(дни от старта) | n  | PF   | Sharpe | ret%")
    print("-" * 60)
    pos_pf = 0
    pos_sh = 0
    total = 0
    start = t_min
    idx = 0
    while start < t_max:
        end = start + win_ms
        chunk = [r for r in all_rows if start <= r[0] < end]
        if chunk:
            n, pf, sh, ret = _window_metrics(chunk, n_sleeves)
            d0 = (start - t_min) // _DAY_MS
            d1 = (end - t_min) // _DAY_MS
            pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
            print(
                f"  {idx:2d} | {d0:4d}-{d1:4d}          | {n:3d} | "
                f"{pf_s:>4s} | {sh:+5.2f} | {ret:+6.2f}"
            )
            total += 1
            if pf > 1.0:
                pos_pf += 1
            if sh > 0.0:
                pos_sh += 1
        start = end
        idx += 1
    if total:
        print("-" * 60)
        print(
            f"Окон: {total} | PF>1: {pos_pf}/{total} "
            f"({pos_pf / total * 100:.0f}%) | Sharpe>0: {pos_sh}/{total} "
            f"({pos_sh / total * 100:.0f}%)"
        )
        print(
            "Вердикт: лид устойчив если ≥70% окон PF>1 и Sharpe>0; "
            "иначе хрупкий (тащат отдельные окна, как LTC)."
        )


if __name__ == "__main__":
    main()
