"""Risk-слой gold-bot: размер позиции от риска + circuit breakers."""

from __future__ import annotations

from risk.config import RiskConfig, load_risk_config
from risk.engine import (
    EntryContext,
    RiskDecision,
    RiskEngine,
    RiskState,
    Sizing,
    compute_sizing,
)

__all__ = [
    "EntryContext",
    "RiskConfig",
    "RiskDecision",
    "RiskEngine",
    "RiskState",
    "Sizing",
    "compute_sizing",
    "load_risk_config",
]
