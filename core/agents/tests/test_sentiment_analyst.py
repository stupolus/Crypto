"""Unit-тесты ``SentimentAnalystAgent``."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from core.agents import (
    AgentExecutionError,
    AgentRequest,
    SentimentAnalystAgent,
)


def _anthropic_response(text: str) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-4-5",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 100, "output_tokens": 40},
    }


def _valid_context() -> dict[str, Any]:
    return {
        "symbol": "BTC-USDT",
        "twitter_sentiment_score": "0.45",
        "twitter_top_mentions": "[]",
        "news_headlines": "[]",
        "funding_rate": "0.01",
        "tg_channels_summary": "neutral",
    }


def _valid_payload_json(score: float = 0.5, conf: float = 0.7) -> str:
    return (
        '{"sentiment_score": ' + str(score) + ", "
        '"key_events": ["BTC ETF inflow", "Saylor покупает"], '
        '"risk_flags": ["Fed announce tomorrow"], '
        '"confidence": ' + str(conf) + "}"
    )


@pytest.mark.asyncio
async def test_sentiment_analyst_valid_response() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(_valid_payload_json()))
            )
            agent = SentimentAnalystAgent(api_key="test-key", client=client)
            resp = await agent.run(AgentRequest(context=_valid_context()))
    assert resp.payload["sentiment_score"] == 0.5
    assert resp.payload["confidence"] == 0.7
    assert resp.payload["key_events"] == ["BTC ETF inflow", "Saylor покупает"]
    assert resp.payload["risk_flags"] == ["Fed announce tomorrow"]


@pytest.mark.asyncio
async def test_sentiment_analyst_score_out_of_range() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(
                    200, json=_anthropic_response(_valid_payload_json(score=2.5))
                )
            )
            agent = SentimentAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="out of range"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_sentiment_analyst_negative_score_valid() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(
                    200, json=_anthropic_response(_valid_payload_json(score=-0.85))
                )
            )
            agent = SentimentAnalystAgent(api_key="test-key", client=client)
            resp = await agent.run(AgentRequest(context=_valid_context()))
    assert resp.payload["sentiment_score"] == -0.85


@pytest.mark.asyncio
async def test_sentiment_analyst_confidence_out_of_range() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(
                    200, json=_anthropic_response(_valid_payload_json(conf=1.5))
                )
            )
            agent = SentimentAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="out of range"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_sentiment_analyst_score_not_number() -> None:
    payload = (
        '{"sentiment_score": "bullish", "key_events": [], "risk_flags": [], "confidence": 0.5}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = SentimentAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="must be number"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_sentiment_analyst_key_events_not_list() -> None:
    payload = (
        '{"sentiment_score": 0.3, '
        '"key_events": "just one string", '
        '"risk_flags": [], '
        '"confidence": 0.5}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = SentimentAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="key_events must be list"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_sentiment_analyst_risk_flags_not_strings() -> None:
    payload = (
        '{"sentiment_score": 0.3, "key_events": [], "risk_flags": [1, 2, 3], "confidence": 0.5}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = SentimentAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="must contain only strings"):
                await agent.run(AgentRequest(context=_valid_context()))


def test_sentiment_analyst_class_attrs() -> None:
    assert SentimentAnalystAgent.name == "sentiment_analyst"
    assert SentimentAnalystAgent.model == "claude-haiku-4-5"
    assert "sentiment-classifier" in SentimentAnalystAgent.system_prompt
    assert "sentiment_score" in SentimentAnalystAgent.required_response_keys
