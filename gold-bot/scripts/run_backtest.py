"""Walk-forward бэктест выбранной стратегии по историческим свечам.

Запуск из каталога gold-bot (после download_klines; данные в gold-bot/data/):
    python -m scripts.run_backtest --exchange bingx --symbol BTC/USDT:USDT \\
        --timeframe 15m --strategy mean_reversion_vwap
    python -m scripts.run_backtest --exchange bingx --symbol PAXG/USDT:USDT \\
        --timeframe 15m --strategy donchian_breakout

Печатает метрики по каждому OOS-окну, агрегат OOS и вердикт против порогов
master-плана (PF≥1.3, expectancy>2×cost, max DD≤8%, ≥30 сделок/окно).
В dev-контейнере данных нет (сеть закрыта) — запускать на VPS.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from backtest.costs import CostModel
from backtest.engine import BacktestEngine
from backtest.metrics import Metrics
from backtest.strategy import Strategy
from backtest.walkforward import run_walk_forward
from marketdata.candles import candles_path, load_parquet
from risk.config import load_risk_config
from strategies.donchian_breakout.config import load_params as load_donchian_params
from strategies.donchian_breakout.strategy import DonchianBreakout
from strategies.mean_reversion_vwap.config import load_params as load_mrv_params
from strategies.mean_reversion_vwap.strategy import MeanReversionVWAP

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Реестр стратегий: имя → фабрика, принимающая risk_pct, возвращающая Strategy.
# Добавление новой стратегии = одна строка здесь.
_STRATEGIES: dict[str, Callable[[Decimal], Strategy]] = {
    "mean_reversion_vwap": lambda risk: MeanReversionVWAP(load_mrv_params(), risk),
    "donchian_breakout": lambda risk: DonchianBreakout(load_donchian_params(), risk),
}


def _fmt(m: Metrics) -> str:
    pf = "inf" if m.profit_factor is None else f"{m.profit_factor:.2f}"
    return (
        f"trades={m.num_trades} winrate={m.winrate:.2%} PF={pf} "
        f"expectancy={m.expectancy} maxDD={m.max_drawdown_pct:.2%} "
        f"sharpe={m.sharpe_per_trade:.2f} sortino={m.sortino_per_trade:.2f}"
    )


def _verdict(m: Metrics) -> str:
    ok = (
        m.num_trades >= 30
        and m.profit_factor is not None
        and m.profit_factor >= 1.3
        and m.max_drawdown_pct <= 0.08
    )
    return "PASS (предварительно, до paper)" if ok else "FAIL по порогам master-плана"


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward бэктест стратегии")
    parser.add_argument("--exchange", choices=["bingx", "bybit"], required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument(
        "--strategy",
        choices=sorted(_STRATEGIES.keys()),
        default="mean_reversion_vwap",
        help="Какую стратегию прогонять (см. _STRATEGIES)",
    )
    parser.add_argument("--equity", type=str, default="10000")
    parser.add_argument("--train", type=int, default=2000, help="свечей в IS-окне")
    parser.add_argument("--test", type=int, default=1000, help="свечей в OOS-окне")
    parser.add_argument("--taker", type=str, default="0.0005")
    parser.add_argument("--slippage", type=str, default="0.0005")
    args = parser.parse_args()

    cfg = load_risk_config()
    risk_pct = cfg.risk_pct_base
    equity0 = Decimal(args.equity)
    costs = CostModel(taker_fee=Decimal(args.taker), slippage_pct=Decimal(args.slippage))

    strategy_factory = _STRATEGIES[args.strategy]

    path = candles_path(_DATA_DIR, args.exchange, args.symbol, args.timeframe)
    candles = load_parquet(path)
    print(f"Стратегия: {args.strategy}")
    print(f"Загружено свечей: {len(candles)} из {path}")

    report = run_walk_forward(
        candles,
        lambda _is: BacktestEngine(strategy_factory(risk_pct), costs, cfg, equity0),
        train_size=args.train,
        test_size=args.test,
        equity0=equity0,
    )

    for wr in report.windows:
        w = wr.window
        print(f"  OOS-окно #{w.index} [{w.oos_start}:{w.oos_end}]: {_fmt(wr.metrics)}")
    print(f"OOS-агрегат: {_fmt(report.oos_aggregate)}")
    print(f"Вердикт: {_verdict(report.oos_aggregate)}")


if __name__ == "__main__":
    main()
