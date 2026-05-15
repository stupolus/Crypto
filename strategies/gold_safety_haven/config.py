"""Загрузка параметров GoldSafetyHaven стратегии.

Reuse `StrategyConfig` из btc_breakout — алгоритм идентичен, отличается
только YAML. Подробности — ``plans/19-asset-strategies.md``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from strategies.btc_breakout.config import (
    StrategyConfig,
    StrategyConfigError,
)
from strategies.btc_breakout.config import (
    load_config as _load_config,
)

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"

__all__ = ["StrategyConfigError", "get_default_config", "load_config"]


def load_config(path: Path | None = None) -> StrategyConfig:
    return _load_config(path or DEFAULT_CONFIG_PATH)


@lru_cache(maxsize=1)
def get_default_config() -> StrategyConfig:
    return load_config(None)
