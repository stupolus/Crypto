"""Factory для построения AgentTeam одной командой.

Использование:

    team = build_default_team()  # читает ANTHROPIC_API_KEY из .env

    team = build_default_team(api_key="sk-test-...")  # явный override

    # Для тестов:
    team = build_mock_team(coordinator_action="BUY")  # все MockAgent
"""

from __future__ import annotations

from typing import Any

import httpx

from core.agents.coordinator import CoordinatorAgent
from core.agents.macro_analyst import MacroAnalystAgent
from core.agents.market_analyst import MarketAnalystAgent
from core.agents.mock import MockAgent
from core.agents.risk_overseer import RiskOverseerAgent
from core.agents.sentiment_analyst import SentimentAnalystAgent
from core.agents.settings import AnthropicSettings
from core.agents.team import AgentTeam


class AgentFactoryError(Exception):
    """Конфигурация агентов невалидна (нет API ключа, etc)."""


def build_default_team(
    *,
    api_key: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> AgentTeam:
    """Собрать AgentTeam с реальными Anthropic agents.

    ``api_key`` — если не задан, читается из ANTHROPIC_API_KEY env / .env.
    ``client`` — опциональный shared httpx.AsyncClient (для эффективности
    connection pooling между всеми 5 агентами).

    Raises AgentFactoryError если API ключа нет вообще.
    """
    if api_key is None:
        settings = AnthropicSettings()
        if not settings.configured:
            raise AgentFactoryError(
                "ANTHROPIC_API_KEY не задан в .env и не передан в аргумент. "
                "Получи ключ на console.anthropic.com и положи в .env."
            )
        api_key = settings.api_key
    assert api_key is not None  # для mypy

    return AgentTeam(
        market_analyst=MarketAnalystAgent(api_key=api_key, client=client),
        sentiment_analyst=SentimentAnalystAgent(api_key=api_key, client=client),
        risk_overseer=RiskOverseerAgent(api_key=api_key, client=client),
        macro_analyst=MacroAnalystAgent(api_key=api_key, client=client),
        coordinator=CoordinatorAgent(api_key=api_key, client=client),
    )


def build_mock_team(
    *,
    coordinator_action: str = "HOLD",
    coordinator_size_risk_pct: float = 0.0,
    coordinator_confidence: float = 0.5,
    market_state: str = "RANGE_BOUND",
    sentiment_score: float = 0.0,
    risk_approved: bool = True,
    risk_max_pct: float = 1.0,
    macro_regime: str = "NEUTRAL",
) -> AgentTeam:
    """Собрать AgentTeam с MockAgent во всех 5 ролях — для тестов / dev.

    Все параметры с дефолтами. Подставляются в mock_payload.
    """
    market_payload: dict[str, Any] = {
        "state": market_state,
        "key_levels": {"support": [], "resistance": []},
        "volatility": "normal",
        "liquidity": "normal",
        "notes": "mock",
    }
    sentiment_payload: dict[str, Any] = {
        "sentiment_score": sentiment_score,
        "key_events": [],
        "risk_flags": [],
        "confidence": 0.7,
    }
    risk_payload: dict[str, Any] = {
        "approved": risk_approved,
        "max_risk_pct": risk_max_pct,
        "reasoning": "mock",
        "concerns": [],
        "confidence": 0.7,
    }
    macro_payload: dict[str, Any] = {
        "regime": macro_regime,
        "confidence": 0.6,
        "rationale": "mock",
        "portfolio_hedge_recommended": False,
        "hedge_size_pct_of_long_exposure": 0.0,
        "risk_off_drivers": [],
        "duration_estimate_hours": 24,
    }
    coordinator_payload: dict[str, Any] = {
        "action": coordinator_action,
        "size_risk_pct": coordinator_size_risk_pct,
        "entry_price": "80500" if coordinator_action in {"BUY", "SELL"} else None,
        "sl_price": "79800" if coordinator_action in {"BUY", "SELL"} else None,
        "tp_prices": ["81200"] if coordinator_action in {"BUY", "SELL"} else [],
        "reasoning": "mock decision",
        "composite_confidence": coordinator_confidence,
    }

    return AgentTeam(
        market_analyst=MockAgent(name="market_analyst", mock_payload=market_payload),
        sentiment_analyst=MockAgent(name="sentiment_analyst", mock_payload=sentiment_payload),
        risk_overseer=MockAgent(name="risk_overseer", mock_payload=risk_payload),
        macro_analyst=MockAgent(name="macro_analyst", mock_payload=macro_payload),
        coordinator=MockAgent(name="coordinator", mock_payload=coordinator_payload),
    )
