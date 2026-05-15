"""Layer 6 Post-Mortem learning (plan #18).

Захватывает context каждой сделки (signal + subagent decisions),
хранит outcome после закрытия. Используется offline для:
- классификации mistakes
- past-mistakes context injection (RAG для Layer 3 промптов)

Hot path: только writes. Reads — offline / weekly review.
"""

from core.postmortem.exit_tracker import ExitTracker
from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.mistake_classifier import (
    MistakeClassifierAgent,
    trade_outcome_to_context,
)
from core.postmortem.mistake_writer import (
    MistakeClassification,
    build_mistake_markdown,
    mistake_filename,
    write_mistake_document,
)
from core.postmortem.models import (
    DecisionContext,
    ExitData,
    ExitReason,
    OrderSide,
    TradeOutcome,
)
from core.postmortem.past_mistakes import (
    PastMistakesRetriever,
    PastMistakeSummary,
    summaries_to_prompt_text,
)

__all__ = [
    "DecisionContext",
    "ExitData",
    "ExitReason",
    "ExitTracker",
    "MistakeClassification",
    "MistakeClassifierAgent",
    "OrderSide",
    "PastMistakeSummary",
    "PastMistakesRetriever",
    "TradeOutcome",
    "TradeOutcomeLogger",
    "build_mistake_markdown",
    "mistake_filename",
    "summaries_to_prompt_text",
    "trade_outcome_to_context",
    "write_mistake_document",
]
