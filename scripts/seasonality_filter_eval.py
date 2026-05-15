"""Оценка сезонного фильтра на стоковом бэктесте (план 24 фаза 24.2).

Запуск:
    .venv/bin/python -m scripts.seasonality_filter_eval

Берёт стоковые перпы BingX, гоняет trend_ema_4h (как в плане 22),
затем применяет ЧЕСТНЫЙ look-ahead-safe фильтр: отбрасывает сделки,
вход которых пришёлся на BEAR-месяц БАЗОВОГО актива (климатология
10 лет — известна априори). Печатает before/after по OOS.

Это не торговый код — оффлайн-аналитика: улучшает ли сезонность
результат стокового перпа (go/no-go для трека акций).
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal

from parsers.macro.seasonality import MonthBias, compute_month_stats, month_bias

# Перп BingX → тикер базового актива Yahoo.
_PERP_UNDERLYING: dict[str, str] = {
    "NCSKTSLA2USD-USDT": "TSLA",
    "NCSKNVDA2USD-USDT": "NVDA",
    "NCSKAAPL2USD-USDT": "AAPL",
    "AAPLX-USDT": "AAPL",
}
_CANDLE = "data/candles/{lower}-4h.jsonl"
_OPS = "ops"


def _latest_oos_json(after_mtime: float) -> str | None:
    files = [
        f for f in glob.glob(f"{_OPS}/backtest-oos-*.json") if os.path.getmtime(f) > after_mtime
    ]
    return max(files, key=os.path.getmtime) if files else None


def _metrics(pnls: list[Decimal]) -> tuple[int, str, str, str]:
    if not pnls:
        return 0, "—", "—", "—"
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    pf = "inf" if losses == 0 else f"{wins / losses:.2f}"
    wr = f"{sum(1 for p in pnls if p > 0) / len(pnls) * 100:.0f}%"
    return len(pnls), pf, wr, f"{sum(pnls):+.2f}%"


def main() -> None:
    print("perp            | underlying | OOS baseline            | OOS season-filtered")
    print("-" * 90)
    for perp, under in _PERP_UNDERLYING.items():
        candle = _CANDLE.format(lower=perp.lower())
        if not os.path.exists(candle):
            print(f"{perp:15s} | {under:10s} | НЕТ свечей {candle}")
            continue
        t0 = max(
            (os.path.getmtime(f) for f in glob.glob(f"{_OPS}/backtest-oos-*.json")),
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
                perp,
                "--candles",
                candle,
                "--split-fraction",
                "0.5",
            ],
            check=True,
            capture_output=True,
        )
        oos = _latest_oos_json(t0)
        if oos is None:
            print(f"{perp:15s} | {under:10s} | бэктест не дал OOS json")
            continue
        with open(oos) as fh:
            trades = json.load(fh)["trades"]
        stats = compute_month_stats(under)
        note = "(Yahoo недоступен → фильтр no-op)" if not stats else ""
        base_pnls = [Decimal(str(t["pnl_pct"])) for t in trades]
        kept: list[Decimal] = []
        for t in trades:
            month = datetime.fromtimestamp(t["entry"]["timestamp_ms"] / 1000, tz=UTC).month
            if month_bias(stats, month) is not MonthBias.BEAR:
                kept.append(Decimal(str(t["pnl_pct"])))
        bn, bpf, bwr, bpnl = _metrics(base_pnls)
        kn, kpf, kwr, kpnl = _metrics(kept)
        print(
            f"{perp:15s} | {under:10s} | "
            f"n={bn:2d} PF={bpf:>4s} wr={bwr:>4s} {bpnl:>8s} | "
            f"n={kn:2d} PF={kpf:>4s} wr={kwr:>4s} {kpnl:>8s} {note}"
        )


if __name__ == "__main__":
    main()
