"""Trend following EMA cross 4h."""

from strategies.trend_ema_4h.config import (
    TrendEmaConfig,
    TrendEmaConfigError,
    get_default_config,
    load_config,
)
from strategies.trend_ema_4h.strategy import TrendEmaStrategy

__all__ = [
    "TrendEmaConfig",
    "TrendEmaConfigError",
    "TrendEmaStrategy",
    "get_default_config",
    "load_config",
]
