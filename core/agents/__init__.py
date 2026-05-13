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

from core.agents.anthropic import AnthropicAgent
from core.agents.base import (
    AgentError,
    AgentExecutionError,
    AgentRequest,
    AgentResponse,
    BaseAgent,
)
from core.agents.coordinator import CoordinatorAgent
from core.agents.macro_analyst import MacroAnalystAgent
from core.agents.market_analyst import MarketAnalystAgent
from core.agents.mock import MockAgent
from core.agents.risk_overseer import RiskOverseerAgent
from core.agents.sentiment_analyst import SentimentAnalystAgent
from core.agents.signal import SignalAction, SignalCandidate
from core.agents.team import AgentTeam, TeamDecision

__all__ = [
    "AgentError",
    "AgentExecutionError",
    "AgentRequest",
    "AgentResponse",
    "AgentTeam",
    "AnthropicAgent",
    "BaseAgent",
    "CoordinatorAgent",
    "MacroAnalystAgent",
    "MarketAnalystAgent",
    "MockAgent",
    "RiskOverseerAgent",
    "SentimentAnalystAgent",
    "SignalAction",
    "SignalCandidate",
    "TeamDecision",
]
