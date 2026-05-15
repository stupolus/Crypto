"""Загрузка параметров US session breakout стратегии."""

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


class UsSessionConfig(_StrictModel):
    symbol: str
    timeframe: Literal["5m", "15m", "30m"]

    asian_start_hour_utc: int = Field(ge=0, le=23)
    asian_end_hour_utc: int = Field(ge=0, le=23)
    us_start_hour_utc: int = Field(ge=0, le=23)
    us_end_hour_utc: int = Field(ge=0, le=23)
    eod_close_hour_utc: int = Field(ge=0, le=23)

    min_range_pct: float = Field(gt=0)
    max_range_pct: float = Field(gt=0)

    stop_min_pct: float = Field(gt=0)
    tp1_r_multiple: float = Field(gt=0)

    risk_tier: RiskTier = RiskTier.B

    @model_validator(mode="after")
    def _check_hours(self) -> UsSessionConfig:
        if self.asian_end_hour_utc != self.us_start_hour_utc:
            raise ValueError(
                "asian_end_hour_utc must equal us_start_hour_utc (continuous transition)"
            )
        if self.us_end_hour_utc <= self.us_start_hour_utc:
            raise ValueError("us_end_hour_utc must be > us_start_hour_utc")
        if self.min_range_pct >= self.max_range_pct:
            raise ValueError("min_range_pct must be < max_range_pct")
        return self


class UsSessionConfigError(Exception):
    """Ошибка загрузки/валидации config."""


def load_config(path: Path | None = None) -> UsSessionConfig:
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise UsSessionConfigError(f"config not found: {target}") from e
    except yaml.YAMLError as e:
        raise UsSessionConfigError(f"config YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise UsSessionConfigError(f"config root must be mapping, got {type(raw).__name__}")
    try:
        return UsSessionConfig.model_validate(raw)
    except ValidationError as e:
        raise UsSessionConfigError(f"config validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_default_config() -> UsSessionConfig:
    return load_config(None)
