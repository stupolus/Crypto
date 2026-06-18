"""Конфиг рисков: pydantic-модель + загрузка из YAML.

Числа — зеркало risk-profile.md. Код ссылается сюда, не хардкодит.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "risk.yaml"


class RiskConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_pct_base: Decimal
    risk_pct_max: Decimal
    risk_pct_min: Decimal

    max_effective_leverage: Decimal
    min_stop_distance_pct: Decimal
    maintenance_margin_rate: Decimal
    liq_buffer_min_frac: Decimal

    daily_stop_pct: Decimal
    weekly_stop_pct: Decimal
    monthly_stop_pct: Decimal
    global_killswitch_dd_pct: Decimal
    max_consecutive_losses: int

    max_positions_total: int
    max_positions_per_class: int
    max_positions_per_symbol: int

    max_trades_per_day: int
    max_trades_per_symbol_per_day: int
    min_seconds_between_trades_same_symbol: int

    cost_edge_min_ratio: Decimal
    spread_max_mult: Decimal


def load_risk_config(path: Path | str | None = None) -> RiskConfig:
    target = Path(path) if path is not None else _DEFAULT_PATH
    with open(target, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return RiskConfig.model_validate(data)
