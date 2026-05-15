"""Параметры trend EMA 4h стратегии."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from core.risk import RiskTier

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TrendEmaConfig(_StrictModel):
    symbol: str
    timeframe: Literal["1h", "4h", "1d"]
    ema_fast: int = Field(gt=0)
    ema_slow: int = Field(gt=0)
    atr_window: int = Field(gt=0)
    sl_atr_multiplier: float = Field(gt=0)
    min_ema_spread_pct: float = Field(ge=0)
    stop_min_pct: float = Field(gt=0)
    tp1_r_multiple: float = Field(gt=0)
    risk_tier: RiskTier = RiskTier.B

    @model_validator(mode="after")
    def _check_ema_order(self) -> TrendEmaConfig:
        if self.ema_fast >= self.ema_slow:
            raise ValueError("ema_fast must be < ema_slow")
        return self


class TrendEmaConfigError(Exception):
    pass


def load_config(path: Path | None = None) -> TrendEmaConfig:
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise TrendEmaConfigError(f"config not found: {target}") from e
    except yaml.YAMLError as e:
        raise TrendEmaConfigError(f"YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise TrendEmaConfigError(f"config root must be mapping, got {type(raw).__name__}")
    try:
        return TrendEmaConfig.model_validate(raw)
    except ValidationError as e:
        raise TrendEmaConfigError(f"validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_default_config() -> TrendEmaConfig:
    return load_config(None)
