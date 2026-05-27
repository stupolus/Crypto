"""box_breakout (#008, план 50): пробой консолидационного бокса."""

from strategies.box_breakout.config import (
    BoxBreakoutConfig,
    BoxBreakoutConfigError,
    get_default_config,
    load_config,
)
from strategies.box_breakout.strategy import BoxBreakoutStrategy

__all__ = [
    "BoxBreakoutConfig",
    "BoxBreakoutConfigError",
    "BoxBreakoutStrategy",
    "get_default_config",
    "load_config",
]
