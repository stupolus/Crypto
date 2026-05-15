"""Event-driven backtester для стратегий."""

from core.backtest.config import BacktestConfig, get_default_config, load_config
from core.backtest.engine import BacktestEngine
from core.backtest.metrics import compute_summary
from core.backtest.models import (
    BacktestResult,
    BacktestSummary,
    FillEvent,
    OpenPosition,
    Strategy,
    StrategyContext,
    Trade,
)

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "BacktestSummary",
    "FillEvent",
    "OpenPosition",
    "Strategy",
    "StrategyContext",
    "Trade",
    "compute_summary",
    "get_default_config",
    "load_config",
]
