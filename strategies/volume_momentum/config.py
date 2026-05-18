"""Параметры volume_momentum (объём подтверждает импульс, план 28)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.risk import RiskTier

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VolumeMomentumConfig(_StrictModel):
    symbol: str
    timeframe: Literal["1h", "4h", "1d"]
    vol_n: int = Field(gt=1)  # окно среднего объёма
    vol_mult: float = Field(gt=1.0)  # всплеск = объём > mult×среднего
    atr_window: int = Field(gt=0)
    sl_atr_multiplier: float = Field(gt=0)
    stop_min_pct: float = Field(gt=0)
    tp1_r_multiple: float = Field(gt=0)
    risk_tier: RiskTier = RiskTier.B


class VolumeMomentumConfigError(Exception):
    pass


def load_config(path: Path | None = None) -> VolumeMomentumConfig:
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise VolumeMomentumConfigError(f"config not found: {target}") from e
    except yaml.YAMLError as e:
        raise VolumeMomentumConfigError(f"YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise VolumeMomentumConfigError(f"config root must be mapping, got {type(raw).__name__}")
    try:
        return VolumeMomentumConfig.model_validate(raw)
    except ValidationError as e:
        raise VolumeMomentumConfigError(f"validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_default_config() -> VolumeMomentumConfig:
    return load_config(None)
