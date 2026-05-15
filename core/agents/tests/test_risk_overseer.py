"""Unit-тесты ``RiskOverseerAgent``."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from core.agents import (
    AgentExecutionError,
    AgentRequest,
    RiskOverseerAgent,
)


def _anthropic_response(text: str) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-4-7",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 300, "output_tokens": 80},
    }


def _valid_context() -> dict[str, Any]:
    return {
        "trade_proposal_json": '{"symbol": "BTC-USDT", "side": "BUY", "risk_pct": 1.0}',
        "equity": "99999.94",
        "open_positions_json": "[]",
        "daily_pnl": "-0.5",
        "recent_trades_json": "[]",
        "correlation_json": "{}",
    }


def _approved_payload(approved: bool = True, max_risk: float = 1.0, conf: float = 0.7) -> str:
    return (
        '{"approved": '
        + str(approved).lower()
        + ", "
        + '"max_risk_pct": '
        + str(max_risk)
        + ", "
        + '"reasoning": "Сетап чистый, корреляция ниже порога, daily PnL в пределах.", '
        + '"concerns": ["BTC dom растёт"], '
        + '"confidence": '
        + str(conf)
        + "}"
    )


@pytest.mark.asyncio
async def test_risk_overseer_approves_valid_trade() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(_approved_payload()))
            )
            agent = RiskOverseerAgent(api_key="test-key", client=client)
            resp = await agent.run(AgentRequest(context=_valid_context()))
    assert resp.payload["approved"] is True
    assert resp.payload["max_risk_pct"] == 1.0
    assert resp.payload["confidence"] == 0.7


@pytest.mark.asyncio
async def test_risk_overseer_veto_valid() -> None:
    """approved=False — это valid response (veto)."""
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(
                    200, json=_anthropic_response(_approved_payload(approved=False, max_risk=0.0))
                )
            )
            agent = RiskOverseerAgent(api_key="test-key", client=client)
            resp = await agent.run(AgentRequest(context=_valid_context()))
    assert resp.payload["approved"] is False
    assert resp.payload["max_risk_pct"] == 0.0


@pytest.mark.asyncio
async def test_risk_overseer_approved_not_bool() -> None:
    payload = (
        '{"approved": "yes", "max_risk_pct": 1.0, '
        '"reasoning": "x", "concerns": [], "confidence": 0.5}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = RiskOverseerAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="approved must be bool"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_risk_overseer_max_risk_out_of_range() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(
                    200, json=_anthropic_response(_approved_payload(max_risk=5.0))
                )
            )
            agent = RiskOverseerAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="out of range"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_risk_overseer_max_risk_zero_allowed() -> None:
    """max_risk_pct=0 валиден — означает 'не торгуем сейчас'."""
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(
                    200, json=_anthropic_response(_approved_payload(max_risk=0.0))
                )
            )
            agent = RiskOverseerAgent(api_key="test-key", client=client)
            resp = await agent.run(AgentRequest(context=_valid_context()))
    assert resp.payload["max_risk_pct"] == 0.0


@pytest.mark.asyncio
async def test_risk_overseer_empty_reasoning_rejected() -> None:
    payload = (
        '{"approved": false, "max_risk_pct": 0.0, '
        '"reasoning": "  ", "concerns": [], "confidence": 0.5}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = RiskOverseerAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="reasoning must be non-empty"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_risk_overseer_concerns_not_strings() -> None:
    payload = (
        '{"approved": true, "max_risk_pct": 1.0, '
        '"reasoning": "ok", "concerns": [1, 2, "valid"], "confidence": 0.7}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = RiskOverseerAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="must contain only strings"):
                await agent.run(AgentRequest(context=_valid_context()))


def test_risk_overseer_class_attrs() -> None:
    assert RiskOverseerAgent.name == "risk_overseer"
    assert RiskOverseerAgent.model == "claude-opus-4-7"
    assert "Chief Risk Officer" in RiskOverseerAgent.system_prompt
    assert "veto power" in RiskOverseerAgent.system_prompt
    assert "approved" in RiskOverseerAgent.required_response_keys
