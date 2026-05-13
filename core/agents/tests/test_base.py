"""Unit-тесты ``core.agents.base`` + ``MockAgent``."""

from __future__ import annotations

import pytest

from core.agents import (
    AgentExecutionError,
    AgentRequest,
    AgentResponse,
    BaseAgent,
    MockAgent,
)


@pytest.mark.asyncio
async def test_mock_agent_returns_configured_payload() -> None:
    agent = MockAgent(
        name="test",
        mock_payload={"state": "TRENDING_UP", "confidence": 0.8},
    )
    resp = await agent.run(AgentRequest(context={}))
    assert resp.payload == {"state": "TRENDING_UP", "confidence": 0.8}
    assert resp.model == "mock"
    assert resp.raw_text.startswith("<mock")


@pytest.mark.asyncio
async def test_mock_agent_validates_required_keys() -> None:
    agent = MockAgent(
        name="missing",
        mock_payload={"foo": "bar"},
        required_keys=("state",),
    )
    with pytest.raises(AgentExecutionError, match="payload invalid"):
        await agent.run(AgentRequest(context={}))


@pytest.mark.asyncio
async def test_mock_agent_with_valid_required_keys() -> None:
    agent = MockAgent(
        name="ok",
        mock_payload={"state": "X", "extra": "y"},
        required_keys=("state",),
    )
    resp = await agent.run(AgentRequest(context={}))
    assert resp.payload["state"] == "X"


def test_agent_request_immutable() -> None:
    from dataclasses import FrozenInstanceError

    req = AgentRequest(context={"a": 1})
    with pytest.raises(FrozenInstanceError):
        req.context = {"a": 2}  # type: ignore[misc]


def test_agent_response_default_fields() -> None:
    resp = AgentResponse(
        payload={"k": "v"},
        raw_text="text",
        model="claude-opus-4-7",
    )
    assert resp.tokens_in == 0
    assert resp.tokens_out == 0
    assert resp.metadata == {}


class _FailingAgent(BaseAgent):
    """Имитирует exception в _execute."""

    name = "failing"

    async def _execute(self, req: AgentRequest) -> AgentResponse:
        raise RuntimeError("boom from LLM API")

    def _validate_payload(self, payload: dict[str, object]) -> None:
        return None


@pytest.mark.asyncio
async def test_execution_error_wraps_underlying_exception() -> None:
    agent = _FailingAgent()
    with pytest.raises(AgentExecutionError, match="failing execution failed"):
        await agent.run(AgentRequest(context={}))
