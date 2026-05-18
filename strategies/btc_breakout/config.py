"""Загрузка параметров BTC breakout стратегии."""

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


DirectionBias = Literal["both", "long_only", "short_only"]


class StrategyConfig(_StrictModel):
    symbol: str
    timeframe: Literal["5m", "15m", "1h", "4h"]

    donchian_n: int = Field(gt=0)

    atr_window: int = Field(gt=0)
    atr_percentile_min: float = Field(ge=0, le=1)
    atr_percentile_lookback: int = Field(gt=0)

    volume_sma_window: int = Field(gt=0)
    volume_multiplier: float = Field(gt=0)

    funding_rate_max_pct: float = Field(ge=0)

    stop_min_pct: float = Field(gt=0)
    tp1_r_multiple: float = Field(gt=0)

    tp2_trailing_ema: int = Field(gt=0)

    risk_tier: RiskTier = RiskTier.B

    # Направленный bias: для safe-haven assets (gold) — long_only, для shorts
    # bias (например, structurally weakening token) — short_only.
    # См. plans/19-asset-strategies.md §«Параметры (обоснование)».
    direction_bias: DirectionBias = "both"


class StrategyConfigError(Exception):
    """Ошибка загрузки/валидации strategy-config."""


def load_config(path: Path | None = None) -> StrategyConfig:
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise StrategyConfigError(f"strategy config not found: {target}") from e
    except yaml.YAMLError as e:
        raise StrategyConfigError(f"strategy YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise StrategyConfigError(f"strategy config root must be mapping, got {type(raw).__name__}")
    try:
        return StrategyConfig.model_validate(raw)
    except ValidationError as e:
        raise StrategyConfigError(f"strategy config validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_default_config() -> StrategyConfig:
    return load_config(None)
