"""Unit-тесты ``core.agents.anthropic.AnthropicAgent``."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from core.agents import (
    AgentExecutionError,
    AgentRequest,
    AnthropicAgent,
)
from core.agents.anthropic import _extract_json_payload


class _TestAgent(AnthropicAgent):
    """Минимальный concrete agent для тестов."""

    name = "test_agent"
    model = "claude-sonnet-4-6"
    system_prompt = "You are a test."
    user_prompt_template = "Tell me about {topic}."
    required_response_keys = ("verdict",)


def _anthropic_response(text: str, in_tokens: int = 50, out_tokens: int = 20) -> dict[str, Any]:
    """Шаблон Anthropic API response."""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": in_tokens, "output_tokens": out_tokens},
    }


@pytest.mark.asyncio
async def test_anthropic_agent_successful_call() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(
                    200,
                    json=_anthropic_response('{"verdict": "BUY", "confidence": 0.85}'),
                )
            )
            agent = _TestAgent(api_key="test-key", client=client)
            resp = await agent.run(AgentRequest(context={"topic": "BTC"}))
    assert resp.payload == {"verdict": "BUY", "confidence": 0.85}
    assert resp.tokens_in == 50
    assert resp.tokens_out == 20
    assert resp.model == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_anthropic_agent_parses_code_block() -> None:
    """Anthropic иногда оборачивает JSON в ```json блок."""
    wrapped = 'Анализ показывает:\n```json\n{"verdict": "HOLD"}\n```'
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(wrapped))
            )
            agent = _TestAgent(api_key="test-key", client=client)
            resp = await agent.run(AgentRequest(context={"topic": "BTC"}))
    assert resp.payload == {"verdict": "HOLD"}


@pytest.mark.asyncio
async def test_anthropic_agent_required_keys_validation_fails() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(
                    200,
                    json=_anthropic_response('{"some_other_key": "value"}'),
                )
            )
            agent = _TestAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="missing required keys"):
                await agent.run(AgentRequest(context={"topic": "X"}))


@pytest.mark.asyncio
async def test_anthropic_agent_http_error_wrapped() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(429, json={"error": "rate_limited"})
            )
            agent = _TestAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="HTTP 429"):
                await agent.run(AgentRequest(context={"topic": "X"}))


@pytest.mark.asyncio
async def test_anthropic_agent_missing_context_key() -> None:
    async with httpx.AsyncClient() as client:
        agent = _TestAgent(api_key="test-key", client=client)
        with pytest.raises(AgentExecutionError, match="missing context key"):
            await agent.run(AgentRequest(context={}))  # нет 'topic'


@pytest.mark.asyncio
async def test_anthropic_agent_unparsable_json() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(
                    200,
                    json=_anthropic_response("Это просто текст, без JSON"),
                )
            )
            agent = _TestAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="Could not extract JSON"):
                await agent.run(AgentRequest(context={"topic": "X"}))


def test_empty_api_key_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty api_key"):
        _TestAgent(api_key="")


def test_extract_json_inline() -> None:
    text = 'Анализ BTC: рынок в TRENDING_UP. {"state": "TRENDING_UP"}'
    assert _extract_json_payload(text) == {"state": "TRENDING_UP"}


def test_extract_json_pure_object() -> None:
    text = '{"a": 1, "b": "x"}'
    assert _extract_json_payload(text) == {"a": 1, "b": "x"}


def test_extract_json_with_code_block() -> None:
    text = 'Here it is:\n```json\n{"k": "v"}\n```\nDone.'
    assert _extract_json_payload(text) == {"k": "v"}


def test_extract_json_raises_on_no_json() -> None:
    with pytest.raises(AgentExecutionError, match="Could not extract JSON"):
        _extract_json_payload("Plain text, no braces here.")


@pytest.mark.asyncio
async def test_anthropic_agent_sends_correct_headers() -> None:
    """Проверяем что x-api-key + anthropic-version + content-type правильные."""
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            route = mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response('{"verdict": "BUY"}'))
            )
            agent = _TestAgent(api_key="sk-test-12345", client=client)
            await agent.run(AgentRequest(context={"topic": "ETH"}))

    assert route.called
    req = route.calls.last.request
    assert req.headers["x-api-key"] == "sk-test-12345"
    assert req.headers["anthropic-version"] == "2023-06-01"
    assert req.headers["content-type"] == "application/json"

    body = json.loads(req.content)
    assert body["model"] == "claude-sonnet-4-6"
    assert body["system"] == "You are a test."
    assert body["messages"] == [{"role": "user", "content": "Tell me about ETH."}]
