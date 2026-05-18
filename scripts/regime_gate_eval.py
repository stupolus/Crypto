"""Оценка S&P risk-off гейта на глубоком крипто-скрине (план 24).

Гипотеза: ценовые крипто-стратегии теряют деньги преимущественно
в risk-off режиме широкого рынка (S&P ниже своей 10-мес SMA).
Look-ahead-safe гейт: отбросить сделки, чей вход пришёлся на
(год,месяц) с RISK_OFF (trailing SMA — только прошлое).

Запуск:
    .venv/bin/python -m scripts.regime_gate_eval

Агрегирует OOS-сделки по 13 ликвидным перпам (24-мес 4h),
печатает before/after. Оффлайн-аналитика, не торговый код.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal

from parsers.macro.seasonality import MarketRegime, regime_history

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


def _latest_oos(after: float) -> str | None:
    fs = [f for f in glob.glob(f"{_OPS}/backtest-oos-*.json") if os.path.getmtime(f) > after]
    return max(fs, key=os.path.getmtime) if fs else None


def _metrics(pnls: list[Decimal]) -> str:
    if not pnls:
        return "n=0"
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    pf = "inf" if losses == 0 else f"{wins / losses:.2f}"
    wr = sum(1 for p in pnls if p > 0) / len(pnls) * 100
    return f"n={len(pnls):3d} PF={pf:>4s} wr={wr:4.0f}% pnl={sum(pnls):+8.2f}%"


def main() -> None:
    regimes = regime_history("^GSPC")
    if not regimes:
        print("Yahoo ^GSPC недоступен → гейт no-op, тест неинформативен")
        return
    base: list[Decimal] = []
    gated: list[Decimal] = []
    dropped_off = 0
    for sym in _COINS:
        candle = f"data/candles/{sym.lower()}-4h.jsonl"
        if not os.path.exists(candle):
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
                sym,
                "--candles",
                candle,
                "--split-fraction",
                "0.5",
            ],
            check=True,
            capture_output=True,
        )
        oos = _latest_oos(t0)
        if oos is None:
            continue
        with open(oos) as fh:
            trades = json.load(fh)["trades"]
        for t in trades:
            pnl = Decimal(str(t["pnl_pct"]))
            base.append(pnl)
            dt = datetime.fromtimestamp(t["entry"]["timestamp_ms"] / 1000, tz=UTC)
            if regimes.get((dt.year, dt.month)) is MarketRegime.RISK_OFF:
                dropped_off += 1
            else:
                gated.append(pnl)
    print(f"Покрытие режима: {len(regimes)} мес. Отброшено risk-off: {dropped_off}")
    print(f"BASELINE (все OOS):       {_metrics(base)}")
    print(f"RISK-OFF GATED (только on): {_metrics(gated)}")


if __name__ == "__main__":
    main()
