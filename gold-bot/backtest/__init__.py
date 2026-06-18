"""Бэктест gold-bot: event-driven движок, cost-модель, метрики, walk-forward."""

from __future__ import annotations

from backtest.costs import CostModel
from backtest.engine import BacktestEngine, BacktestResult, Trade
from backtest.metrics import Metrics, compute_metrics
from backtest.strategy import Signal, Strategy
from backtest.walkforward import (
    WalkForwardReport,
    Window,
    WindowResult,
    make_windows,
    run_walk_forward,
)

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "CostModel",
    "Metrics",
    "Signal",
    "Strategy",
    "Trade",
    "WalkForwardReport",
    "Window",
    "WindowResult",
    "compute_metrics",
    "make_windows",
    "run_walk_forward",
]
