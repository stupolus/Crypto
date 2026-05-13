"""LLM-агенты для торгового бота (Layer 3 из plans/17).

Каждый агент — специализированный LLM-call с собственным промптом и
output-схемой. Координатор синтезирует решения нескольких агентов
в финальный TradeProposal перед Layer 4 (Risk Engine).

Базовые классы:
- ``BaseAgent`` — async interface ``prompt → JSON response``
- ``AgentResponse`` / ``AgentRequest`` — типизированные модели

Имплементации (по мере добавления):
- ``MarketAnalystAgent`` (Sonnet 4.6) — техническая картина
- ``SentimentAnalystAgent`` (Haiku 4.5) — Twitter + news
- ``RiskOverseerAgent`` (Opus 4.7) — veto power
- ``MacroAnalystAgent`` (Sonnet 4.6) — DXY/VIX/S&P regime
- ``CoordinatorAgent`` (Opus 4.7) — синтез всех ответов

См. plans/17 §3 для детальных промптов.
"""

from core.agents.base import (
    AgentError,
    AgentExecutionError,
    AgentRequest,
    AgentResponse,
    BaseAgent,
)
from core.agents.mock import MockAgent

__all__ = [
    "AgentError",
    "AgentExecutionError",
    "AgentRequest",
    "AgentResponse",
    "BaseAgent",
    "MockAgent",
]
