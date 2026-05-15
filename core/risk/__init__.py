"""Risk engine: размер позиции + circuit breakers.

Stateless движок. Inputs от стратегии → одно решение (Approval | Rejection).
Все числа — из `бизнес/риск-профиль.md` через `config.yaml`.
"""

from core.risk.config import RiskConfig, get_default_config, load_config
from core.risk.correlation_gate import CorrelationDecision, check_correlation
from core.risk.engine import RiskEngine
from core.risk.models import (
    RejectionCode,
    RiskApproval,
    RiskDecision,
    RiskInputs,
    RiskRejection,
    RiskTier,
    Side,
)

__all__ = [
    "CorrelationDecision",
    "RejectionCode",
    "RiskApproval",
    "RiskConfig",
    "RiskDecision",
    "RiskEngine",
    "RiskInputs",
    "RiskRejection",
    "RiskTier",
    "Side",
    "check_correlation",
    "get_default_config",
    "load_config",
]
