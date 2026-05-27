"""Параметры composite_signal (план 31).

Числа — дефолты детекторов из core/signals (НЕ подобраны под бэктест:
бэктеста нет — нет истории OI/liq/CVD; валидация — forward на демо,
план 31). При изменении: сначала план, потом сюда.
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


class CompositeConfig(_Strict):
    symbol: str
    timeframe: Literal["5m", "15m", "1h", "4h"]

    # Funding-extreme детектор.
    funding_min_history: int = Field(gt=0)
    funding_pct_high: float = Field(gt=0, le=1)
    funding_pct_low: float = Field(ge=0, lt=1)

    # Liquidation-sweep детектор.
    liq_spike_min: float = Field(gt=0)
    liq_min_baseline_usd: float = Field(ge=0)
    liq_baseline_n: int = Field(gt=0)

    # CVD order-flow детектор (3-й голос — план 35).
    cvd_lookback: int = Field(gt=0)
    order_flow_threshold: float = Field(gt=0, lt=1)

    # OI-gate (подтверждение направления, не голос).
    oi_lookback: int = Field(gt=0)
    oi_rise_pct: float = Field(gt=0)
    oi_fall_pct: float = Field(gt=0)

    # Exits / risk.
    atr_window: int = Field(gt=0)
    atr_sl_multiplier: float = Field(gt=0)
    stop_min_pct: float = Field(gt=0)
    tp1_r_multiple: float = Field(gt=0)
    risk_tier: RiskTier = RiskTier.B

    direction_bias: Literal["both", "long_only", "short_only"] = "both"

    # ── v2-улучшения (план 43). Дефолты = поведение v1 (демо не меняется) ──
    # 43.1 Confidence-gate: skip если confidence_raw < порога. 0 = выкл.
    min_confidence: float = Field(default=0.0, ge=0, le=1)
    # 43.2 Адаптивный TP R по силе сигнала. off → фиксированный tp1_r.
    tp1_r_adaptive: bool = False
    tp1_r_min: float | None = Field(default=None, gt=0)
    tp1_r_max: float | None = Field(default=None, gt=0)
    # 43.3 ATR-percentile режим-фильтр. [0,1] = пропускает всё (выкл).
    atr_pct_min: float = Field(default=0.0, ge=0, le=1)
    atr_pct_max: float = Field(default=1.0, ge=0, le=1)
    atr_pct_lookback: int = Field(default=200, gt=0)

    # ── v3 (план 44). Default None = выкл; v2 не затронут ──
    # 44.1 Session-time gate: список разрешённых UTC-часов (0..23). None = любые.
    session_hours_utc: tuple[int, ...] | None = None


class CompositeConfigError(Exception):
    """Ошибка загрузки/валидации config."""


def load_config(path: Path | None = None) -> CompositeConfig:
    target = path or DEFAULT_CONFIG_PATH
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise CompositeConfigError(f"config not found: {target}") from e
    except yaml.YAMLError as e:
        raise CompositeConfigError(f"YAML parse error: {e}") from e
    if not isinstance(raw, dict):
        raise CompositeConfigError(f"config root must be mapping, got {type(raw).__name__}")
    try:
        return CompositeConfig.model_validate(raw)
    except ValidationError as e:
        raise CompositeConfigError(f"config validation failed: {e}") from e


@lru_cache(maxsize=1)
def get_default_config() -> CompositeConfig:
    return load_config(None)
