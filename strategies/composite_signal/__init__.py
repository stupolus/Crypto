"""composite_signal — стратегия принципа 3 (план 31)."""

from strategies.composite_signal.config import (
    CompositeConfig,
    CompositeConfigError,
    get_default_config,
    load_config,
)
from strategies.composite_signal.strategy import CompositeSignalStrategy

__all__ = [
    "CompositeConfig",
    "CompositeConfigError",
    "CompositeSignalStrategy",
    "get_default_config",
    "load_config",
]
