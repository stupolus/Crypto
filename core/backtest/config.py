"""Загрузка ``core/backtest/config.yaml``."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FeesConfig(_StrictModel):
    taker_pct: float = Field(ge=0, lt=10)
    maker_pct: float = Field(ge=0, lt=10)


class BacktestConfig(_StrictModel):
    fees: FeesConfig
    slippage_bps: float = Field(ge=0, lt=1000)
    initial_equity: float = Field(gt=0)

    @property
    def initial_equity_decimal(self) -> Decimal:
        return Decimal(str(self.initial_equity))


class BacktestConfigError(Exception):
    """Ошибка загрузки/валидации backtest-config."""


def load_config(path: Path | None = None) -> BacktestConfig:
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise BacktestConfigError(f"backtest config not found: {target}") from e
    except yaml.YAMLError as e:
        raise BacktestConfigError(f"backtest YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise BacktestConfigError(
            f"backtest config root must be mapping, got {type(raw).__name__}"
        )
    try:
        return BacktestConfig.model_validate(raw)
    except ValidationError as e:
        raise BacktestConfigError(f"backtest config validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_default_config() -> BacktestConfig:
    return load_config(None)
