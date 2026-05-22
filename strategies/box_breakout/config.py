"""Параметры box_breakout (план 50). Дефолты из теории/видео #008,
НЕ подобраны под бэктест (AGENTS.md anti-overfitting)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.risk import RiskTier

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BoxBreakoutConfig(_Strict):
    symbol: str
    timeframe: Literal["5m", "15m", "1h", "4h", "1d"]

    box_n: int = Field(gt=1)
    box_max_width_pct: float = Field(gt=0)
    vol_sma_window: int = Field(gt=0)
    breakout_vol_mult: float = Field(gt=0)

    atr_window: int = Field(gt=0)
    atr_sl_mult: float = Field(gt=0)
    stop_min_pct: float = Field(gt=0)
    tp_r: float = Field(gt=0)

    risk_tier: RiskTier = RiskTier.B
    direction_bias: Literal["both", "long_only", "short_only"] = "both"


class BoxBreakoutConfigError(Exception):
    """Ошибка загрузки/валидации config."""


def load_config(path: Path | None = None) -> BoxBreakoutConfig:
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise BoxBreakoutConfigError(f"config not found: {target}") from e
    except yaml.YAMLError as e:
        raise BoxBreakoutConfigError(f"YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise BoxBreakoutConfigError(f"config root must be mapping, got {type(raw).__name__}")
    try:
        return BoxBreakoutConfig.model_validate(raw)
    except ValidationError as e:
        raise BoxBreakoutConfigError(f"config validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_default_config() -> BoxBreakoutConfig:
    return load_config(None)
