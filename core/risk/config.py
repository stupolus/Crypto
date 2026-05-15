"""Загрузка и валидация ``core/risk/config.yaml``.

Числа здесь — зеркало `бизнес/риск-профиль.md`. Источник истины —
markdown-файл. При изменении значения: сначала правим риск-профиль
(там обоснование), потом config.yaml.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RiskPctConfig(_StrictModel):
    B: float = Field(gt=0, le=10)
    A: float = Field(gt=0, le=10)
    A_PLUS: float = Field(gt=0, le=10)


class LimitsConfig(_StrictModel):
    max_effective_leverage: float = Field(gt=0, le=125)
    stop_min_pct: float = Field(gt=0, lt=100)
    liquidation_buffer_ratio: float = Field(gt=0, lt=1)


class CircuitBreakersConfig(_StrictModel):
    daily_loss_pct: float = Field(lt=0)
    weekly_loss_pct: float = Field(lt=0)
    monthly_loss_pct: float = Field(lt=0)
    max_daily_trades: int = Field(gt=0)
    max_consecutive_losses: int = Field(gt=0)


class RiskConfig(_StrictModel):
    risk_pct: RiskPctConfig
    limits: LimitsConfig
    circuit_breakers: CircuitBreakersConfig


class RiskConfigError(Exception):
    """Ошибка загрузки/валидации risk-config."""


def load_config(path: Path | None = None) -> RiskConfig:
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise RiskConfigError(f"risk config not found: {target}") from e
    except yaml.YAMLError as e:
        raise RiskConfigError(f"risk config YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise RiskConfigError(f"risk config root must be mapping, got {type(raw).__name__}")
    try:
        return RiskConfig.model_validate(raw)
    except ValidationError as e:
        raise RiskConfigError(f"risk config validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_default_config() -> RiskConfig:
    return load_config(None)
