"""Бэктест gold-bot: event-driven движок, cost-модель, метрики, walk-forward."""

from __future__ import annotations

from backtest.costs import CostModel
from backtest.engine import BacktestEngine, BacktestResult, Trade
from backtest.metrics import Metrics, compute_metrics
from backtest.strategy import Signal, Strategy

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "CostModel",
    "Metrics",
    "Signal",
    "Strategy",
    "Trade",
    "compute_metrics",
]
