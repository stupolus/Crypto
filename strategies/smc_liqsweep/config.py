"""Параметры smc_liqsweep (liquidity-sweep reversion, план 32)."""

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


class SmcLiqsweepConfig(_StrictModel):
    symbol: str
    timeframe: Literal["5m", "15m", "30m"]
    swing_lookback: int = Field(gt=1)  # окно swing high/low (ликвидность)
    sweep_k_atr: float = Field(gt=0)  # прокол хвостом ≥ k·ATR за уровень
    ema_fast: int = Field(gt=0)
    ema_slow: int = Field(gt=0)
    trend_block_pct: float = Field(gt=0)  # фильтр сильного дневного тренда
    atr_window: int = Field(gt=0)
    sl_buf_atr: float = Field(gt=0)  # буфер SL за экстремум свипа
    tp_r: float = Field(gt=0)  # цель в R от риска
    stop_min_pct: float = Field(gt=0)
    risk_tier: RiskTier = RiskTier.B

    @model_validator(mode="after")
    def _chk(self) -> SmcLiqsweepConfig:
        if self.ema_fast >= self.ema_slow:
            raise ValueError("ema_fast must be < ema_slow")
        return self


class SmcLiqsweepConfigError(Exception):
    pass


def load_config(path: Path | None = None) -> SmcLiqsweepConfig:
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise SmcLiqsweepConfigError(f"config not found: {target}") from e
    except yaml.YAMLError as e:
        raise SmcLiqsweepConfigError(f"YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise SmcLiqsweepConfigError(f"config root must be mapping, got {type(raw).__name__}")
    try:
        return SmcLiqsweepConfig.model_validate(raw)
    except ValidationError as e:
        raise SmcLiqsweepConfigError(f"validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_default_config() -> SmcLiqsweepConfig:
    return load_config(None)
