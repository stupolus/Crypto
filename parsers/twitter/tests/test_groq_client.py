"""Unit-тесты ``GroqClient``.

Использует respx чтобы мокать api.groq.com — никаких реальных API-вызовов.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from parsers.twitter import GroqClient, GroqError, TweetClassification


def _groq_response(content_dict: dict[str, Any]) -> dict[str, Any]:
    """Шаблон Groq Chat Completions response (OpenAI format)."""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "llama-3.1-70b-versatile",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(content_dict),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140},
    }


@pytest.mark.asyncio
async def test_groq_client_classifies_bullish_tweet() -> None:
    async with httpx.AsyncClient() as http_client:
        with respx.mock(base_url="https://api.groq.com") as mock:
            mock.post("/openai/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json=_groq_response(
                        {
                            "sentiment": 0.7,
                            "tokens": ["BTC"],
                            "relevance": "high",
                            "is_breaking": False,
                            "summary": "MicroStrategy buys more BTC.",
                        }
                    ),
                )
            )
            groq = GroqClient(api_key="gsk-test", client=http_client)
            result = await groq.classify_tweet("$MSTR just bought 1000 more BTC")

    assert isinstance(result, TweetClassification)
    assert result.sentiment == 0.7
    assert result.tokens == ("BTC",)
    assert result.relevance == "high"
    assert result.is_breaking is False


@pytest.mark.asyncio
async def test_groq_client_classifies_breaking_news() -> None:
    async with httpx.AsyncClient() as http_client:
        with respx.mock(base_url="https://api.groq.com") as mock:
            mock.post("/openai/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json=_groq_response(
                        {
                            "sentiment": -0.8,
                            "tokens": ["BTC", "ETH"],
                            "relevance": "high",
                            "is_breaking": True,
                            "summary": "FBI seizes 50K BTC from exchange.",
                        }
                    ),
                )
            )
            groq = GroqClient(api_key="gsk-test", client=http_client)
            result = await groq.classify_tweet("BREAKING: FBI seizes...")
    assert result.is_breaking is True
    assert result.sentiment == -0.8
    assert result.tokens == ("BTC", "ETH")


@pytest.mark.asyncio
async def test_groq_client_http_error_wrapped() -> None:
    async with httpx.AsyncClient() as http_client:
        with respx.mock(base_url="https://api.groq.com") as mock:
            mock.post("/openai/v1/chat/completions").mock(
                return_value=httpx.Response(429, json={"error": "rate_limit"})
            )
            groq = GroqClient(api_key="gsk-test", client=http_client)
            with pytest.raises(GroqError, match="HTTP 429"):
                await groq.classify_tweet("test")


@pytest.mark.asyncio
async def test_groq_client_non_json_response() -> None:
    """Если Groq вернул не-JSON — GroqError."""
    response = _groq_response({})  # стартуем с валидного шаблона
    # Заменяем content на не-JSON
    response["choices"][0]["message"]["content"] = "Sorry, I cannot..."

    async with httpx.AsyncClient() as http_client:
        with respx.mock(base_url="https://api.groq.com") as mock:
            mock.post("/openai/v1/chat/completions").mock(
                return_value=httpx.Response(200, json=response)
            )
            groq = GroqClient(api_key="gsk-test", client=http_client)
            with pytest.raises(GroqError, match="non-JSON"):
                await groq.classify_tweet("test")


@pytest.mark.asyncio
async def test_groq_client_missing_field() -> None:
    async with httpx.AsyncClient() as http_client:
        with respx.mock(base_url="https://api.groq.com") as mock:
            mock.post("/openai/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json=_groq_response(
                        {
                            "sentiment": 0.5,
                            "tokens": ["BTC"],
                            "relevance": "high",
                            "is_breaking": False,
                            # missing "summary"
                        }
                    ),
                )
            )
            groq = GroqClient(api_key="gsk-test", client=http_client)
            with pytest.raises(GroqError, match="missing field"):
                await groq.classify_tweet("test")


@pytest.mark.asyncio
async def test_groq_client_sentiment_out_of_range() -> None:
    async with httpx.AsyncClient() as http_client:
        with respx.mock(base_url="https://api.groq.com") as mock:
            mock.post("/openai/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json=_groq_response(
                        {
                            "sentiment": 2.5,  # >1
                            "tokens": ["BTC"],
                            "relevance": "high",
                            "is_breaking": False,
                            "summary": "out of range",
                        }
                    ),
                )
            )
            groq = GroqClient(api_key="gsk-test", client=http_client)
            with pytest.raises(GroqError, match="out of"):
                await groq.classify_tweet("test")


@pytest.mark.asyncio
async def test_groq_client_invalid_relevance() -> None:
    async with httpx.AsyncClient() as http_client:
        with respx.mock(base_url="https://api.groq.com") as mock:
            mock.post("/openai/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json=_groq_response(
                        {
                            "sentiment": 0.5,
                            "tokens": ["BTC"],
                            "relevance": "epic",  # invalid
                            "is_breaking": False,
                            "summary": "bad",
                        }
                    ),
                )
            )
            groq = GroqClient(api_key="gsk-test", client=http_client)
            with pytest.raises(GroqError, match="relevance="):
                await groq.classify_tweet("test")


def test_empty_api_key_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty api_key"):
        GroqClient(api_key="")


@pytest.mark.asyncio
async def test_groq_client_sends_correct_request() -> None:
    """Проверяем что body содержит правильные fields."""
    async with httpx.AsyncClient() as http_client:
        with respx.mock(base_url="https://api.groq.com") as mock:
            route = mock.post("/openai/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json=_groq_response(
                        {
                            "sentiment": 0.0,
                            "tokens": [],
                            "relevance": "low",
                            "is_breaking": False,
                            "summary": "ok",
                        }
                    ),
                )
            )
            groq = GroqClient(api_key="gsk-key-123", client=http_client)
            await groq.classify_tweet("test message")

    assert route.called
    req = route.calls.last.request
    assert req.headers["authorization"] == "Bearer gsk-key-123"
    body = json.loads(req.content)
    assert body["temperature"] == 0.0  # deterministic
    assert body["response_format"]["type"] == "json_object"
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["content"] == "test message"
