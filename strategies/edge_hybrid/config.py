"""Параметры edge_hybrid (scalp ∨ SMC, план 33)."""

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


class EdgeHybridConfig(_StrictModel):
    symbol: str
    timeframe: Literal["5m", "15m", "30m"]
    # Общее
    ema_fast: int = Field(gt=0)
    ema_slow: int = Field(gt=0)
    trend_block_pct: float = Field(gt=0)
    atr_window: int = Field(gt=0)
    stop_min_pct: float = Field(gt=0)
    risk_tier: RiskTier = RiskTier.B
    # Включение веток (для атрибуции edge; деф. все вкл.)
    enable_a: bool = True
    enable_b: bool = True
    enable_c: bool = True
    # Ветка A — mean-reversion к якорю
    anchor_ema: int = Field(gt=1)
    entry_k_atr: float = Field(gt=0)
    sl_k_atr: float = Field(gt=0)
    # Ветка B — liquidity-sweep + reclaim
    swing_lookback: int = Field(gt=1)
    sweep_k_atr: float = Field(gt=0)
    sl_buf_atr: float = Field(gt=0)
    tp_r: float = Field(gt=0)
    # Ветка C — volatility-box breakout + volume-bias (PR #152 #008)
    box_window: int = Field(gt=1)
    box_max_atr: float = Field(gt=0)  # высота бокса ≤ k·ATR = консолидация
    strong_body_frac: float = Field(gt=0, le=1)  # тело/диапазон свечи пробоя
    box_tp_r: float = Field(gt=0)

    @model_validator(mode="after")
    def _chk(self) -> EdgeHybridConfig:
        if self.ema_fast >= self.ema_slow:
            raise ValueError("ema_fast must be < ema_slow")
        return self


class EdgeHybridConfigError(Exception):
    pass


def load_config(path: Path | None = None) -> EdgeHybridConfig:
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise EdgeHybridConfigError(f"config not found: {target}") from e
    except yaml.YAMLError as e:
        raise EdgeHybridConfigError(f"YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise EdgeHybridConfigError(f"config root must be mapping, got {type(raw).__name__}")
    try:
        return EdgeHybridConfig.model_validate(raw)
    except ValidationError as e:
        raise EdgeHybridConfigError(f"validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_default_config() -> EdgeHybridConfig:
    return load_config(None)
