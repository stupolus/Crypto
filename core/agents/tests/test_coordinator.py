"""Unit-тесты ``CoordinatorAgent``."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from core.agents import (
    AgentExecutionError,
    AgentRequest,
    CoordinatorAgent,
)


def _anthropic_response(text: str) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-4-7",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 500, "output_tokens": 120},
    }


def _valid_context() -> dict[str, Any]:
    return {
        "signal_json": '{"symbol": "BTC-USDT", "action": "BUY"}',
        "market_analyst_json": '{"state": "TRENDING_UP"}',
        "sentiment_analyst_json": '{"sentiment_score": 0.4}',
        "risk_overseer_json": '{"approved": true, "max_risk_pct": 1.0}',
        "macro_analyst_json": '{"regime": "RISK_ON"}',
    }


def _buy_payload() -> str:
    return (
        '{"action": "BUY", "size_risk_pct": 1.0, '
        '"entry_price": "80500", "sl_price": "79800", '
        '"tp_prices": ["81200", "82000"], '
        '"reasoning": "Все 4 субагента подтверждают breakout. Risk Overseer approve.", '
        '"composite_confidence": 0.72}'
    )


def _hold_payload(reason: str = "Risk Overseer veto") -> str:
    return (
        '{"action": "HOLD", "size_risk_pct": 0.0, '
        '"entry_price": null, "sl_price": null, '
        '"tp_prices": [], '
        '"reasoning": "' + reason + '", '
        '"composite_confidence": 0.3}'
    )


@pytest.mark.asyncio
async def test_coordinator_buy_with_all_fields() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(_buy_payload()))
            )
            agent = CoordinatorAgent(api_key="test-key", client=client)
            resp = await agent.run(AgentRequest(context=_valid_context()))
    assert resp.payload["action"] == "BUY"
    assert resp.payload["size_risk_pct"] == 1.0
    assert resp.payload["entry_price"] == "80500"
    assert resp.payload["tp_prices"] == ["81200", "82000"]


@pytest.mark.asyncio
async def test_coordinator_hold_with_nulls_ok() -> None:
    """HOLD не требует entry/SL цен."""
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(_hold_payload()))
            )
            agent = CoordinatorAgent(api_key="test-key", client=client)
            resp = await agent.run(AgentRequest(context=_valid_context()))
    assert resp.payload["action"] == "HOLD"
    assert resp.payload["size_risk_pct"] == 0.0
    assert resp.payload["entry_price"] is None


@pytest.mark.asyncio
async def test_coordinator_invalid_action_rejected() -> None:
    payload = (
        '{"action": "YOLO", "size_risk_pct": 5.0, '
        '"entry_price": "80000", "sl_price": "79000", '
        '"tp_prices": [], "reasoning": "let go", "composite_confidence": 0.9}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = CoordinatorAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="invalid action 'YOLO'"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_coordinator_buy_without_entry_price_rejected() -> None:
    payload = (
        '{"action": "BUY", "size_risk_pct": 1.0, '
        '"entry_price": null, "sl_price": "79800", '
        '"tp_prices": ["81200"], "reasoning": "ok", "composite_confidence": 0.7}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = CoordinatorAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="entry_price required for action=BUY"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_coordinator_size_out_of_range() -> None:
    payload = (
        '{"action": "BUY", "size_risk_pct": 5.0, '
        '"entry_price": "80000", "sl_price": "79000", '
        '"tp_prices": [], "reasoning": "ok", "composite_confidence": 0.7}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = CoordinatorAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="size_risk_pct.*must be number in"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_coordinator_tp_prices_not_list() -> None:
    payload = (
        '{"action": "BUY", "size_risk_pct": 1.0, '
        '"entry_price": "80000", "sl_price": "79000", '
        '"tp_prices": "81200", "reasoning": "ok", "composite_confidence": 0.7}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = CoordinatorAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="tp_prices must be list"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_coordinator_empty_reasoning_rejected() -> None:
    payload = (
        '{"action": "HOLD", "size_risk_pct": 0.0, '
        '"entry_price": null, "sl_price": null, '
        '"tp_prices": [], "reasoning": " ", "composite_confidence": 0.3}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = CoordinatorAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="reasoning must be non-empty"):
                await agent.run(AgentRequest(context=_valid_context()))


def test_coordinator_class_attrs() -> None:
    assert CoordinatorAgent.name == "coordinator"
    assert CoordinatorAgent.model == "claude-opus-4-7"
    assert "Coordinator" in CoordinatorAgent.system_prompt
    assert "veto" in CoordinatorAgent.system_prompt.lower()
    assert "action" in CoordinatorAgent.required_response_keys
