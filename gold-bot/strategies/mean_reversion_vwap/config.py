"""Параметры стратегии mean-reversion VWAP. Только параметры стратегии;
risk_pct берётся отдельно из risk-profile/RiskConfig."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

_DEFAULT_PATH = Path(__file__).resolve().parent / "config.yaml"


class StrategyParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    vwap_window: int
    atr_period: int
    k_entry: Decimal
    k_stop: Decimal
    session_start_hour_utc: int
    session_end_hour_utc: int
    asset_class: str = "metals"


def load_params(path: Path | str | None = None) -> StrategyParams:
    target = Path(path) if path is not None else _DEFAULT_PATH
    with open(target, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return StrategyParams.model_validate(data)
