"""Layer 6 Post-Mortem learning (plan #18).

Захватывает context каждой сделки (signal + subagent decisions),
хранит outcome после закрытия. Используется offline для:
- классификации mistakes
- past-mistakes context injection (RAG для Layer 3 промптов)

Hot path: только writes. Reads — offline / weekly review.
"""

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.mistake_classifier import (
    MistakeClassifierAgent,
    trade_outcome_to_context,
)
from core.postmortem.models import (
    DecisionContext,
    ExitData,
    ExitReason,
    OrderSide,
    TradeOutcome,
)

__all__ = [
    "DecisionContext",
    "ExitData",
    "ExitReason",
    "MistakeClassifierAgent",
    "OrderSide",
    "TradeOutcome",
    "TradeOutcomeLogger",
    "trade_outcome_to_context",
]
