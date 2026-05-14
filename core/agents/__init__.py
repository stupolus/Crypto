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
from core.agents.evaluate import (
    MacroContextData,
    MarketContextData,
    RunnerStateSnapshot,
    SentimentContextData,
    evaluate_with_team,
)
from core.agents.factory import AgentFactoryError, build_default_team, build_mock_team
from core.agents.macro_analyst import MacroAnalystAgent
from core.agents.market_analyst import MarketAnalystAgent
from core.agents.market_context_builder import MarketBuilderConfig, MarketContextBuilder
from core.agents.mock import MockAgent
from core.agents.order_request_bridge import build_signal_candidate
from core.agents.risk_overseer import RiskOverseerAgent
from core.agents.sentiment_analyst import SentimentAnalystAgent
from core.agents.signal import SignalAction, SignalCandidate
from core.agents.team import AgentTeam, TeamDecision

__all__ = [
    "AgentError",
    "AgentExecutionError",
    "AgentFactoryError",
    "AgentRequest",
    "AgentResponse",
    "AgentTeam",
    "AnthropicAgent",
    "BaseAgent",
    "CoordinatorAgent",
    "MacroAnalystAgent",
    "MacroContextData",
    "MarketAnalystAgent",
    "MarketBuilderConfig",
    "MarketContextBuilder",
    "MarketContextData",
    "MockAgent",
    "RiskOverseerAgent",
    "RunnerStateSnapshot",
    "SentimentAnalystAgent",
    "SentimentContextData",
    "SignalAction",
    "SignalCandidate",
    "TeamDecision",
    "build_default_team",
    "build_mock_team",
    "build_signal_candidate",
    "evaluate_with_team",
]
