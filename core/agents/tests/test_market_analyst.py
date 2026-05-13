"""Unit-тесты ``MarketAnalystAgent``."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from core.agents import (
    AgentExecutionError,
    AgentRequest,
    MarketAnalystAgent,
)


def _anthropic_response(text: str) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 200, "output_tokens": 60},
    }


def _valid_context() -> dict[str, Any]:
    return {
        "symbol": "BTC-USDT",
        "timeframe": "15m",
        "ohlcv_json": "[]",
        "atr": "100.5",
        "donchian_high": "80929",
        "donchian_low": "80444",
        "ema20": "80700",
        "ema50": "80600",
        "bid_5": "80600",
        "ask_5": "80800",
        "orderbook_imbalance": "0.02",
        "funding_rate": "0.0050",
        "oi_change_24h_pct": "2.3",
    }


def _valid_payload_json(state: str = "TRENDING_UP") -> str:
    return (
        '{"state": "' + state + '", '
        '"key_levels": {"support": [80444, 80100], "resistance": [80929, 81500]}, '
        '"volatility": "normal", '
        '"liquidity": "normal", '
        '"notes": "BTC в умеренном восходящем тренде, ATR в норме."}'
    )


@pytest.mark.asyncio
async def test_market_analyst_valid_response() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(_valid_payload_json()))
            )
            agent = MarketAnalystAgent(api_key="test-key", client=client)
            resp = await agent.run(AgentRequest(context=_valid_context()))
    assert resp.payload["state"] == "TRENDING_UP"
    assert resp.payload["volatility"] == "normal"
    assert resp.payload["liquidity"] == "normal"
    assert resp.payload["key_levels"]["support"] == [80444, 80100]


@pytest.mark.asyncio
async def test_market_analyst_invalid_state_rejected() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(
                    200, json=_anthropic_response(_valid_payload_json(state="MOON"))
                )
            )
            agent = MarketAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="invalid state 'MOON'"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_market_analyst_invalid_volatility_rejected() -> None:
    payload = (
        '{"state": "RANGE_BOUND", '
        '"key_levels": {"support": [], "resistance": []}, '
        '"volatility": "extreme", '
        '"liquidity": "normal", '
        '"notes": "test"}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = MarketAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="invalid volatility 'extreme'"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_market_analyst_invalid_liquidity_rejected() -> None:
    payload = (
        '{"state": "RANGE_BOUND", '
        '"key_levels": {"support": [], "resistance": []}, '
        '"volatility": "normal", '
        '"liquidity": "deep_ocean", '
        '"notes": "test"}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = MarketAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="invalid liquidity 'deep_ocean'"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_market_analyst_key_levels_not_dict_rejected() -> None:
    payload = (
        '{"state": "RANGE_BOUND", '
        '"key_levels": "not_a_dict", '
        '"volatility": "normal", '
        '"liquidity": "normal", '
        '"notes": "test"}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = MarketAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="key_levels must be dict"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_market_analyst_key_levels_missing_resistance() -> None:
    payload = (
        '{"state": "RANGE_BOUND", '
        '"key_levels": {"support": []}, '
        '"volatility": "normal", '
        '"liquidity": "normal", '
        '"notes": "test"}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = MarketAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="missing 'resistance'"):
                await agent.run(AgentRequest(context=_valid_context()))


def test_market_analyst_class_attrs() -> None:
    """Конфиг агента — defaults для подачи в Coordinator."""
    assert MarketAnalystAgent.name == "market_analyst"
    assert MarketAnalystAgent.model == "claude-sonnet-4-6"
    assert "quant-аналитик" in MarketAnalystAgent.system_prompt
    assert "state" in MarketAnalystAgent.required_response_keys
