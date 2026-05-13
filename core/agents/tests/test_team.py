"""Unit-тесты ``AgentTeam`` — orchestrator всех 5 субагентов.

Использует MockAgent для всех subagent'ов чтобы не требовать API.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.agents import (
    AgentExecutionError,
    AgentRequest,
    AgentResponse,
    AgentTeam,
    BaseAgent,
    MockAgent,
)


def _make_team(
    market_payload: dict[str, Any] | None = None,
    sentiment_payload: dict[str, Any] | None = None,
    risk_payload: dict[str, Any] | None = None,
    macro_payload: dict[str, Any] | None = None,
    coordinator_payload: dict[str, Any] | None = None,
) -> AgentTeam:
    return AgentTeam(
        market_analyst=MockAgent(name="market_analyst", mock_payload=market_payload or {}),
        sentiment_analyst=MockAgent(name="sentiment_analyst", mock_payload=sentiment_payload or {}),
        risk_overseer=MockAgent(name="risk_overseer", mock_payload=risk_payload or {}),
        macro_analyst=MockAgent(name="macro_analyst", mock_payload=macro_payload or {}),
        coordinator=MockAgent(name="coordinator", mock_payload=coordinator_payload or {}),
    )


@pytest.mark.asyncio
async def test_team_happy_path() -> None:
    """Все 5 субагентов отвечают, Coordinator возвращает BUY."""
    team = _make_team(
        market_payload={"state": "TRENDING_UP"},
        sentiment_payload={"sentiment_score": 0.5},
        risk_payload={"approved": True, "max_risk_pct": 1.0},
        macro_payload={"regime": "RISK_ON"},
        coordinator_payload={
            "action": "BUY",
            "size_risk_pct": 1.0,
            "entry_price": "80500",
            "sl_price": "79800",
            "tp_prices": ["81200"],
            "reasoning": "All clear",
            "composite_confidence": 0.75,
        },
    )
    decision = await team.evaluate_signal(
        signal_context={"symbol": "BTC-USDT"},
        market_context={},
        sentiment_context={},
        risk_context={},
        macro_context={},
    )
    assert decision.coordinator_payload["action"] == "BUY"
    assert decision.subagent_payloads["macro"] == {"regime": "RISK_ON"}
    assert decision.errors == ()


@pytest.mark.asyncio
async def test_team_macro_cached_on_second_call() -> None:
    """Macro кешируется — второй вызов не идёт в агент."""
    team = _make_team(
        market_payload={},
        sentiment_payload={},
        risk_payload={"approved": True, "max_risk_pct": 1.0},
        macro_payload={"regime": "NEUTRAL"},
        coordinator_payload={
            "action": "HOLD",
            "size_risk_pct": 0.0,
            "entry_price": None,
            "sl_price": None,
            "tp_prices": [],
            "reasoning": "test",
            "composite_confidence": 0.5,
        },
    )
    d1 = await team.evaluate_signal(
        signal_context={},
        market_context={},
        sentiment_context={},
        risk_context={},
        macro_context={},
    )
    d2 = await team.evaluate_signal(
        signal_context={},
        market_context={},
        sentiment_context={},
        risk_context={},
        macro_context={},
    )
    assert d1.macro_cached is False
    assert d2.macro_cached is True


class _FailingAgent(BaseAgent):
    name = "failing"

    async def _execute(self, req: AgentRequest) -> AgentResponse:
        raise AgentExecutionError("simulated API down")

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        return None


@pytest.mark.asyncio
async def test_team_risk_overseer_failure_returns_hold() -> None:
    """Если Risk Overseer упал — safety HOLD."""
    team = AgentTeam(
        market_analyst=MockAgent(name="m", mock_payload={"state": "TRENDING_UP"}),
        sentiment_analyst=MockAgent(name="s", mock_payload={"sentiment_score": 0.5}),
        risk_overseer=_FailingAgent(),
        macro_analyst=MockAgent(name="ma", mock_payload={"regime": "NEUTRAL"}),
        coordinator=MockAgent(name="c", mock_payload={"action": "BUY"}),  # не будет вызван
    )
    decision = await team.evaluate_signal(
        signal_context={},
        market_context={},
        sentiment_context={},
        risk_context={},
        macro_context={},
    )
    assert decision.coordinator_payload["action"] == "HOLD"
    assert "Risk Overseer недоступен" in decision.coordinator_payload["reasoning"]
    assert any("failing" in e for e in decision.errors)


@pytest.mark.asyncio
async def test_team_macro_failure_falls_back_to_neutral() -> None:
    """Если Macro упал — используем fallback regime=NEUTRAL, продолжаем."""
    team = AgentTeam(
        market_analyst=MockAgent(name="m", mock_payload={"state": "TRENDING_UP"}),
        sentiment_analyst=MockAgent(name="s", mock_payload={"sentiment_score": 0.5}),
        risk_overseer=MockAgent(name="r", mock_payload={"approved": True, "max_risk_pct": 1.0}),
        macro_analyst=_FailingAgent(),
        coordinator=MockAgent(
            name="c",
            mock_payload={
                "action": "BUY",
                "size_risk_pct": 1.0,
                "entry_price": "80500",
                "sl_price": "79800",
                "tp_prices": [],
                "reasoning": "ok",
                "composite_confidence": 0.7,
            },
        ),
    )
    decision = await team.evaluate_signal(
        signal_context={},
        market_context={},
        sentiment_context={},
        risk_context={},
        macro_context={},
    )
    # Coordinator всё равно вызвался + macro fallback
    assert decision.coordinator_payload["action"] == "BUY"
    assert decision.subagent_payloads["macro"]["regime"] == "NEUTRAL"


@pytest.mark.asyncio
async def test_team_coordinator_failure_returns_hold() -> None:
    """Если Coordinator упал — HOLD с error в reasoning."""
    team = AgentTeam(
        market_analyst=MockAgent(name="m", mock_payload={"state": "TRENDING_UP"}),
        sentiment_analyst=MockAgent(name="s", mock_payload={"sentiment_score": 0.5}),
        risk_overseer=MockAgent(name="r", mock_payload={"approved": True, "max_risk_pct": 1.0}),
        macro_analyst=MockAgent(name="ma", mock_payload={"regime": "NEUTRAL"}),
        coordinator=_FailingAgent(),
    )
    decision = await team.evaluate_signal(
        signal_context={},
        market_context={},
        sentiment_context={},
        risk_context={},
        macro_context={},
    )
    assert decision.coordinator_payload["action"] == "HOLD"
    assert "Coordinator failed" in decision.coordinator_payload["reasoning"]


@pytest.mark.asyncio
async def test_team_latency_recorded() -> None:
    team = _make_team(
        market_payload={"state": "TRENDING_UP"},
        sentiment_payload={"sentiment_score": 0.5},
        risk_payload={"approved": True, "max_risk_pct": 1.0},
        macro_payload={"regime": "NEUTRAL"},
        coordinator_payload={
            "action": "BUY",
            "size_risk_pct": 1.0,
            "entry_price": "80500",
            "sl_price": "79800",
            "tp_prices": [],
            "reasoning": "ok",
            "composite_confidence": 0.7,
        },
    )
    decision = await team.evaluate_signal(
        signal_context={},
        market_context={},
        sentiment_context={},
        risk_context={},
        macro_context={},
    )
    assert decision.total_latency_ms >= 0
