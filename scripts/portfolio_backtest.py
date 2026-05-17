"""Портфельный бэктест крипто-юниверса (план 22, высокий приоритет).

Лид: одиночные монеты убыточны, но агрегат 13 перпов даёт PF>1.
Проверяем корректно: равновесный портфель (вес 1/N на «рукав»),
ОБЩАЯ компаундящаяся эквити, портфельные Sharpe / maxDD / PF,
раздельно IS и OOS.

Движок BacktestEngine уже применяет RiskEngine-сайзинг → ``pnl``
в $ на базе initial_equity. Портфель: сделки всех монет на одной
оси времени (по выходу), общая эквити растёт на (1/N)·rᵢ.

Допущения (честно): игнорируем лимит одновременных позиций и
маржу; корреляции учтены лишь через фактический тайминг сделок.
Это оценка, не торговый код.

Запуск: .venv/bin/python -m scripts.portfolio_backtest
"""

from __future__ import annotations

import argparse
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
_YEAR_MS = 365 * 24 * 3600 * 1000


def _newest(tag: str, after: float) -> str | None:
    fs = [f for f in glob.glob(f"{_OPS}/backtest-{tag}-*.json") if os.path.getmtime(f) > after]
    return max(fs, key=os.path.getmtime) if fs else None


def _portfolio(rows: list[tuple[int, float, float]], n_sleeves: int) -> str:
    """rows = [(exit_ms, pnl_usd, base_equity)]; вес 1/N, общая эквити."""
    if not rows or n_sleeves == 0:
        return "n=0 (нет сделок)"
    rows.sort(key=lambda r: r[0])
    w = 1.0 / n_sleeves
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    rets: list[float] = []
    wins = 0.0
    losses = 0.0
    for _, pnl_usd, base in rows:
        r = w * (pnl_usd / base)
        equity *= 1.0 + r
        rets.append(r)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
        if pnl_usd > 0:
            wins += pnl_usd
        else:
            losses += -pnl_usd
    span_ms = rows[-1][0] - rows[0][0]
    tpy = len(rows) / (span_ms / _YEAR_MS) if span_ms > 0 else len(rows)
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / len(rets) if len(rets) > 1 else 0.0
    std = math.sqrt(var)
    sharpe = (mean / std * math.sqrt(tpy)) if std > 0 else 0.0
    pf = "inf" if losses == 0 else f"{wins / losses:.2f}"
    wr = sum(1 for x in rets if x > 0) / len(rets) * 100
    return (
        f"n={len(rows):3d} PF={pf:>4s} wr={wr:4.0f}% "
        f"ret={(equity - 1) * 100:+7.2f}% Sharpe={sharpe:+5.2f} "
        f"maxDD={max_dd * 100:4.1f}% sleeves={n_sleeves}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Портфельный бэктест крипты")
    ap.add_argument("--strategy", default="trend_ema_4h")
    args = ap.parse_args()
    by_tag: dict[str, list[tuple[int, float, float]]] = {"is": [], "oos": []}
    sleeves: dict[str, set[str]] = {"is": set(), "oos": set()}
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
                args.strategy,
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
                exit_ms = int(tr["exits"][-1]["timestamp_ms"]) if tr["exits"] else 0
                by_tag[tag].append((exit_ms, float(Decimal(str(tr["pnl"]))), base))
                if tr["exits"]:
                    sleeves[tag].add(sym)
    print(f"Равновесный крипто-портфель ({args.strategy}, 24-мес, вес 1/N):")
    print(f"  IS : {_portfolio(by_tag['is'], len(sleeves['is']))}")
    print(f"  OOS: {_portfolio(by_tag['oos'], len(sleeves['oos']))}")
    print("Критерий приёмки (план 20): OOS PF>1.3 И Sharpe>0.8 И ≥30 сделок.")


if __name__ == "__main__":
    main()
