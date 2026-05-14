"""Unit-тесты ``llm_gate``.

Используем фейковый AgentTeam (monkey-patch ``evaluate_signal``) чтобы
проверить логику gate'а без реальных LLM-вызовов.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from adapters.bingx.private_models import OrderRequest
from core.agents.evaluate import (
    MacroContextData,
    MarketContextData,
    RunnerStateSnapshot,
    SentimentContextData,
)
from core.agents.llm_gate import LLMGateResult, llm_gate
from core.agents.team import AgentTeam, TeamDecision


def _make_request(
    *,
    side: str = "BUY",
    order_type: str = "LIMIT",
    price: Decimal | None = Decimal("80500"),
    sl: Decimal | None = Decimal("80000"),
    tp: Decimal | None = Decimal("82000"),
) -> OrderRequest:
    return OrderRequest(
        symbol="BTC-USDT",
        side=side,
        order_type=order_type,
        quantity=Decimal("0.1"),
        price=price,
        attached_stop_loss=sl,
        attached_take_profit=tp,
    )


def _make_state() -> RunnerStateSnapshot:
    return RunnerStateSnapshot(
        equity=Decimal("1000"),
        daily_pnl_pct=Decimal("0"),
    )


def _make_contexts() -> tuple[MarketContextData, SentimentContextData, MacroContextData]:
    market = MarketContextData(
        ohlcv_recent_json="[]",
        atr="100",
        donchian_high="80929",
        donchian_low="79100",
        ema20="80200",
        ema50="79800",
    )
    sentiment = SentimentContextData()
    macro = MacroContextData()
    return market, sentiment, macro


def _make_team_with_payload(payload: dict[str, Any]) -> AgentTeam:
    team = AsyncMock(spec=AgentTeam)
    team.evaluate_signal.return_value = TeamDecision(
        coordinator_payload=payload,
        subagent_payloads={},
        macro_cached=False,
        total_latency_ms=42,
        total_cost_usd=0.0,
    )
    return team


@pytest.mark.asyncio
async def test_llm_gate_hold_returns_none() -> None:
    team = _make_team_with_payload(
        {"action": "HOLD", "reasoning": "low confidence", "composite_confidence": 0.3}
    )
    market, sentiment, macro = _make_contexts()
    result = await llm_gate(
        team=team,
        order_request=_make_request(),
        strategy_name="btc_breakout",
        timestamp_ms=1_700_000_000_000,
        indicators={"atr": "100"},
        confidence_raw=0.7,
        state=_make_state(),
        market_data=market,
        sentiment_data=sentiment,
        macro_data=macro,
    )
    assert isinstance(result, LLMGateResult)
    assert result.approved_request is None
    assert result.reason == "HOLD"


@pytest.mark.asyncio
async def test_llm_gate_approve_same_side_uses_coordinator_sl_tp() -> None:
    """Coordinator одобрил BUY и предложил более тугой SL — runner использует его."""
    team = _make_team_with_payload(
        {
            "action": "BUY",
            "size_risk_pct": 1.0,
            "entry_price": "80500",
            "sl_price": "80100",  # туже чем оригинал 80000
            "tp_prices": ["82200"],
            "composite_confidence": 0.75,
        }
    )
    market, sentiment, macro = _make_contexts()
    original = _make_request()
    result = await llm_gate(
        team=team,
        order_request=original,
        strategy_name="btc_breakout",
        timestamp_ms=1_700_000_000_000,
        indicators={},
        confidence_raw=0.7,
        state=_make_state(),
        market_data=market,
        sentiment_data=sentiment,
        macro_data=macro,
    )
    assert result.approved_request is not None
    assert result.reason == "APPROVED"
    assert result.approved_request.attached_stop_loss == Decimal("80100")
    assert result.approved_request.attached_take_profit == Decimal("82200")
    # Side / symbol / quantity не меняются
    assert result.approved_request.side == "BUY"
    assert result.approved_request.symbol == "BTC-USDT"
    assert result.approved_request.quantity == original.quantity


@pytest.mark.asyncio
async def test_llm_gate_side_mismatch_treated_as_veto() -> None:
    """Стратегия BUY, Coordinator SELL → veto (защита от случайного переворота)."""
    team = _make_team_with_payload(
        {
            "action": "SELL",
            "size_risk_pct": 1.0,
            "entry_price": "80500",
            "sl_price": "81000",
            "tp_prices": ["79000"],
            "composite_confidence": 0.7,
        }
    )
    market, sentiment, macro = _make_contexts()
    result = await llm_gate(
        team=team,
        order_request=_make_request(side="BUY"),
        strategy_name="btc_breakout",
        timestamp_ms=1_700_000_000_000,
        indicators={},
        confidence_raw=0.7,
        state=_make_state(),
        market_data=market,
        sentiment_data=sentiment,
        macro_data=macro,
    )
    assert result.approved_request is None
    assert "side_mismatch" in result.reason


@pytest.mark.asyncio
async def test_llm_gate_unexpected_action_treated_as_veto() -> None:
    team = _make_team_with_payload({"action": "MAYBE", "composite_confidence": 0.5})
    market, sentiment, macro = _make_contexts()
    result = await llm_gate(
        team=team,
        order_request=_make_request(),
        strategy_name="btc_breakout",
        timestamp_ms=1_700_000_000_000,
        indicators={},
        confidence_raw=0.7,
        state=_make_state(),
        market_data=market,
        sentiment_data=sentiment,
        macro_data=macro,
    )
    assert result.approved_request is None
    assert "unexpected_action" in result.reason


@pytest.mark.asyncio
async def test_llm_gate_uses_original_when_no_overrides() -> None:
    """Coordinator вернул только action — entry/SL/TP остались как у Layer 2."""
    team = _make_team_with_payload(
        {
            "action": "BUY",
            "size_risk_pct": 1.0,
            "entry_price": None,
            "sl_price": None,
            "tp_prices": [],
            "composite_confidence": 0.7,
        }
    )
    market, sentiment, macro = _make_contexts()
    original = _make_request()
    result = await llm_gate(
        team=team,
        order_request=original,
        strategy_name="btc_breakout",
        timestamp_ms=1_700_000_000_000,
        indicators={},
        confidence_raw=0.7,
        state=_make_state(),
        market_data=market,
        sentiment_data=sentiment,
        macro_data=macro,
    )
    assert result.approved_request is not None
    assert result.approved_request.attached_stop_loss == original.attached_stop_loss
    assert result.approved_request.attached_take_profit == original.attached_take_profit
    assert result.approved_request.price == original.price


@pytest.mark.asyncio
async def test_llm_gate_invalid_decimal_in_payload_ignored() -> None:
    """Если Coordinator вернул мусор в sl_price — gate игнорирует и оставляет оригинал."""
    team = _make_team_with_payload(
        {
            "action": "BUY",
            "size_risk_pct": 1.0,
            "entry_price": "80500",
            "sl_price": "not a number",
            "tp_prices": ["-5"],  # отрицательное → ignore
            "composite_confidence": 0.7,
        }
    )
    market, sentiment, macro = _make_contexts()
    original = _make_request()
    result = await llm_gate(
        team=team,
        order_request=original,
        strategy_name="btc_breakout",
        timestamp_ms=1_700_000_000_000,
        indicators={},
        confidence_raw=0.7,
        state=_make_state(),
        market_data=market,
        sentiment_data=sentiment,
        macro_data=macro,
    )
    assert result.approved_request is not None
    assert result.approved_request.attached_stop_loss == original.attached_stop_loss
    assert result.approved_request.attached_take_profit == original.attached_take_profit


@pytest.mark.asyncio
async def test_llm_gate_market_order_ignores_entry_price() -> None:
    """MARKET order: price=None, Coordinator не может его пересчитать."""
    team = _make_team_with_payload(
        {
            "action": "BUY",
            "size_risk_pct": 1.0,
            "entry_price": "80500",  # игнорируется т.к. MARKET
            "sl_price": "80100",
            "tp_prices": [],
            "composite_confidence": 0.7,
        }
    )
    market, sentiment, macro = _make_contexts()
    original = _make_request(order_type="MARKET", price=None)
    result = await llm_gate(
        team=team,
        order_request=original,
        strategy_name="btc_breakout",
        timestamp_ms=1_700_000_000_000,
        indicators={},
        confidence_raw=0.7,
        state=_make_state(),
        market_data=market,
        sentiment_data=sentiment,
        macro_data=macro,
    )
    assert result.approved_request is not None
    assert result.approved_request.price is None  # MARKET остаётся MARKET
    assert result.approved_request.attached_stop_loss == Decimal("80100")
