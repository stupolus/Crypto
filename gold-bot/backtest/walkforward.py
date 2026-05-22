"""Walk-forward харнес: rolling IS/OOS окна + агрегация OOS-метрик.

CLAUDE.md §3,§8: OOS обязателен; параметры не подгоняются на всей истории.
На этом этапе фитинга параметров нет (он появится в champion-challenger,
plan 06) — харнес прогоняет стратегию по последовательным OOS-окнам и
агрегирует, чтобы проверить устойчивость во времени. IS-срез передаётся
фабрике движка для будущего фитинга.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from backtest.engine import BacktestEngine, Trade
from backtest.metrics import Metrics, compute_metrics
from exchanges.models import OHLCV


@dataclass(frozen=True)
class Window:
    index: int
    is_start: int
    is_end: int
    oos_start: int
    oos_end: int


@dataclass(frozen=True)
class WindowResult:
    window: Window
    metrics: Metrics
    trades: list[Trade]


@dataclass(frozen=True)
class WalkForwardReport:
    windows: list[WindowResult]
    oos_aggregate: Metrics


def make_windows(n_candles: int, train_size: int, test_size: int) -> list[Window]:
    """Anchored rolling: IS=[start, start+train), OOS=[.., +test), шаг = test_size."""
    if train_size <= 0 or test_size <= 0:
        raise ValueError("train_size и test_size должны быть > 0")
    windows: list[Window] = []
    idx = 0
    start = 0
    while start + train_size + test_size <= n_candles:
        is_end = start + train_size
        oos_end = is_end + test_size
        windows.append(Window(idx, start, is_end, is_end, oos_end))
        start += test_size
        idx += 1
    return windows


def run_walk_forward(
    candles: Sequence[OHLCV],
    engine_factory: Callable[[list[OHLCV]], BacktestEngine],
    train_size: int,
    test_size: int,
    equity0: Decimal,
) -> WalkForwardReport:
    """Прогнать стратегию по OOS-окнам. engine_factory получает IS-срез (для
    будущего фитинга) и возвращает свежий движок для прогона по OOS."""
    windows = make_windows(len(candles), train_size, test_size)
    results: list[WindowResult] = []
    all_trades: list[Trade] = []
    equity = equity0
    agg_curve: list[Decimal] = [equity0]

    for w in windows:
        is_slice = list(candles[w.is_start : w.is_end])
        oos_slice = list(candles[w.oos_start : w.oos_end])
        engine = engine_factory(is_slice)
        res = engine.run(oos_slice)
        results.append(WindowResult(w, compute_metrics(res.trades, res.equity_curve), res.trades))
        for t in res.trades:
            equity += t.net_pnl
            agg_curve.append(equity)
        all_trades.extend(res.trades)

    return WalkForwardReport(windows=results, oos_aggregate=compute_metrics(all_trades, agg_curve))
