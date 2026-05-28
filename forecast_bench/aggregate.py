"""Свести прогнозы моделей в метрики. Запуск любым venv (нужен pandas).

    python forecast_bench/aggregate.py forecast_bench/out/*.csv

Метрики (горизонт H, прогноз close):
- DirAcc   — доля совпадений знака прогноз-ретёрна и реализованного.
- Corr     — корреляция прогноз-ретёрна с реализованным.
- MAE(ret) — средняя абс. ошибка прогноз-ретёрна, в %.
- PnL/трейд — toy-стратегия sign(pred)*realized, с издержками round-trip.
Бейзлайн: always-long DirAcc = доля баров, где рынок реально вырос.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

COST_RT = 0.001  # 0.1% round-trip (тейкер крипты ~0.04-0.06% на сторону)


def metrics(path: Path) -> dict:
    df = pd.read_csv(path)
    real = df["target"].to_numpy() / df["last_close"].to_numpy() - 1
    pred = df["pred_close"].to_numpy() / df["last_close"].to_numpy() - 1
    sign_match = np.sign(pred) == np.sign(real)
    pnl_gross = np.sign(pred) * real
    pnl_net = pnl_gross - COST_RT
    return {
        "model": path.stem.replace("pred_", ""),
        "n": len(df),
        "DirAcc": sign_match.mean(),
        "Corr": float(np.corrcoef(pred, real)[0, 1]) if len(df) > 2 else float("nan"),
        "MAE_ret%": np.abs(pred - real).mean() * 100,
        "PnL_gross%/trade": pnl_gross.mean() * 100,
        "PnL_net%/trade": pnl_net.mean() * 100,
        "_real": real,
    }


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        raise SystemExit("usage: aggregate.py <pred_csv> [pred_csv ...]")
    res = [metrics(p) for p in paths]
    real = res[0]["_real"]
    base_long = (real > 0).mean()

    print(f"\nBTC-USD 1h | окон={res[0]['n']} | бейзлайн always-long DirAcc={base_long:.3f}")
    print(f"издержки={COST_RT * 100:.2f}% round-trip\n")
    cols = ["model", "DirAcc", "Corr", "MAE_ret%", "PnL_gross%/trade", "PnL_net%/trade"]
    hdr = f"{'model':<10}{'DirAcc':>9}{'Corr':>8}{'MAE_ret%':>10}{'PnLgross':>10}{'PnLnet':>9}"
    print(hdr)
    print("-" * len(hdr))
    for r in res:
        print(
            f"{r['model']:<10}{r['DirAcc']:>9.3f}{r['Corr']:>8.3f}"
            f"{r['MAE_ret%']:>10.3f}{r['PnL_gross%/trade']:>10.3f}{r['PnL_net%/trade']:>9.3f}"
        )
    _ = cols


if __name__ == "__main__":
    main()
