"""Unit-тесты ``MacroAnalystAgent``."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from core.agents import (
    AgentExecutionError,
    AgentRequest,
    MacroAnalystAgent,
)


def _anthropic_response(text: str) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-4-6",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 400, "output_tokens": 100},
    }


def _valid_context() -> dict[str, Any]:
    return {
        "dxy": "104.5",
        "dxy_change_24h_pct": "0.3",
        "vix": "18.2",
        "vix_change_24h_pct": "-2.1",
        "spx": "4500",
        "ndx": "16000",
        "gold": "2050",
        "oil": "75",
        "yield_10y": "4.25",
        "btc_dominance_pct": "52",
        "fed_calendar": "[]",
        "earnings_schedule": "[]",
    }


def _payload(
    regime: str = "NEUTRAL",
    hedge_rec: bool = False,
    hedge_size: float = 0.0,
    duration: int = 24,
) -> str:
    return (
        '{"regime": "' + regime + '", '
        '"confidence": 0.75, '
        '"rationale": "DXY stable, VIX в норме, no major events.", '
        '"portfolio_hedge_recommended": ' + str(hedge_rec).lower() + ", "
        '"hedge_size_pct_of_long_exposure": ' + str(hedge_size) + ", "
        '"risk_off_drivers": [], '
        '"duration_estimate_hours": ' + str(duration) + "}"
    )


@pytest.mark.asyncio
async def test_macro_analyst_valid_neutral() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(_payload()))
            )
            agent = MacroAnalystAgent(api_key="test-key", client=client)
            resp = await agent.run(AgentRequest(context=_valid_context()))
    assert resp.payload["regime"] == "NEUTRAL"
    assert resp.payload["portfolio_hedge_recommended"] is False


@pytest.mark.asyncio
async def test_macro_analyst_risk_off_with_hedge() -> None:
    payload = (
        '{"regime": "RISK_OFF", '
        '"confidence": 0.85, '
        '"rationale": "DXY rocket + VIX spike + NDX dump.", '
        '"portfolio_hedge_recommended": true, '
        '"hedge_size_pct_of_long_exposure": 35.0, '
        '"risk_off_drivers": ["DXY +1.2%", "VIX +12%", "NDX -3%"], '
        '"duration_estimate_hours": 48}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = MacroAnalystAgent(api_key="test-key", client=client)
            resp = await agent.run(AgentRequest(context=_valid_context()))
    assert resp.payload["regime"] == "RISK_OFF"
    assert resp.payload["portfolio_hedge_recommended"] is True
    assert resp.payload["hedge_size_pct_of_long_exposure"] == 35.0
    assert len(resp.payload["risk_off_drivers"]) == 3


@pytest.mark.asyncio
async def test_macro_analyst_invalid_regime_rejected() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(
                    200, json=_anthropic_response(_payload(regime="BULL_MARKET"))
                )
            )
            agent = MacroAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="invalid regime"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_macro_analyst_hedge_size_out_of_range() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(
                    200, json=_anthropic_response(_payload(hedge_size=80.0))
                )
            )
            agent = MacroAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="must be number in \\[0, 50\\]"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_macro_analyst_hedge_recommended_not_bool() -> None:
    payload = (
        '{"regime": "NEUTRAL", '
        '"confidence": 0.5, '
        '"rationale": "ok", '
        '"portfolio_hedge_recommended": "no", '
        '"hedge_size_pct_of_long_exposure": 0, '
        '"risk_off_drivers": [], '
        '"duration_estimate_hours": 24}'
    )
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(payload))
            )
            agent = MacroAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="must be bool"):
                await agent.run(AgentRequest(context=_valid_context()))


@pytest.mark.asyncio
async def test_macro_analyst_negative_duration_rejected() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.anthropic.com") as mock:
            mock.post("/v1/messages").mock(
                return_value=httpx.Response(200, json=_anthropic_response(_payload(duration=-5)))
            )
            agent = MacroAnalystAgent(api_key="test-key", client=client)
            with pytest.raises(AgentExecutionError, match="must be non-negative int"):
                await agent.run(AgentRequest(context=_valid_context()))


def test_macro_analyst_class_attrs() -> None:
    assert MacroAnalystAgent.name == "macro_analyst"
    assert MacroAnalystAgent.model == "claude-sonnet-4-6"
    assert "macro strategist" in MacroAnalystAgent.system_prompt
    assert "regime" in MacroAnalystAgent.required_response_keys
