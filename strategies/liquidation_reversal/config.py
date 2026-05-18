"""Параметры liquidation_reversal. План 21 §«Сетап A1/A2».

Числа — из выжимок курса (бизнес/материалы/курсы/dmitry-shukin/),
НЕ подобраны под бэктест (AGENTS.md anti-overfitting).
"""

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


class LiqReversalConfig(_Strict):
    symbol: str
    timeframe: Literal["5m", "15m", "1h", "4h"]

    # «Значимый экстремум» — Donchian lookback (план 21: ~50).
    level_n: int = Field(gt=0)

    # Триггер: ликвидационный sweep.
    liq_spike_min: float = Field(gt=0)  # recent/baseline ≥ этого
    liq_min_baseline_usd: float = Field(ge=0)
    liq_baseline_n: int = Field(gt=0)

    # Цикл ликвидаций: ждать N свечей после sweep до входа.
    cycle_wait_bars: int = Field(ge=0)

    # OI gate. ``oi_gate_enabled=False`` полностью отключает gate
    # направления (для сред без исторического OI). По умолчанию True —
    # поведение не меняется для существующих конфигов.
    oi_gate_enabled: bool = True
    oi_lookback: int = Field(gt=0)
    oi_rise_pct: float = Field(gt=0)
    oi_fall_pct: float = Field(gt=0)

    # CVD подтверждение: окно для суммы дельты.
    cvd_lookback: int = Field(gt=0)

    # Funding-фильтр: не шортить если funding ≤ этого (доля, не %).
    funding_short_block: float = Field(le=0)

    # Risk / exits.
    stop_min_pct: float = Field(gt=0)
    tp1_r_multiple: float = Field(gt=0)
    risk_tier: RiskTier = RiskTier.B

    # both / long_only / short_only.
    direction_bias: Literal["both", "long_only", "short_only"] = "both"


class LiqReversalConfigError(Exception):
    """Ошибка загрузки/валидации config."""


def load_config(path: Path | None = None) -> LiqReversalConfig:
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise LiqReversalConfigError(f"config not found: {target}") from e
    except yaml.YAMLError as e:
        raise LiqReversalConfigError(f"YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise LiqReversalConfigError(f"config root must be mapping, got {type(raw).__name__}")
    try:
        return LiqReversalConfig.model_validate(raw)
    except ValidationError as e:
        raise LiqReversalConfigError(f"config validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_default_config() -> LiqReversalConfig:
    return load_config(None)
