"""Unit-тесты ``MistakeClassifierAgent`` валидации + helper ``trade_outcome_to_context``."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.agents.base import AgentExecutionError
from core.postmortem.mistake_classifier import (
    MistakeClassifierAgent,
    trade_outcome_to_context,
)
from core.postmortem.models import TradeOutcome


def _make_closed_outcome(**overrides: object) -> TradeOutcome:
    defaults: dict[str, object] = {
        "trade_id": "t1",
        "symbol": "BTC-USDT",
        "side": "BUY",
        "entry_time_ms": 1_700_000_000_000,
        "entry_price": Decimal("80500"),
        "size": Decimal("0.1"),
        "exit_time_ms": 1_700_000_900_000,
        "exit_price": Decimal("80000"),
        "pnl_usd": Decimal("-50"),
        "pnl_pct": Decimal("-0.62"),
        "exit_reason": "SL",
        "holding_time_min": 15,
        "signal_candidate_json": '{"action": "BUY"}',
        "market_analyst_json": '{"state": "TRENDING_UP"}',
        "sentiment_analyst_json": '{"sentiment_score": 0.4}',
        "risk_overseer_json": '{"approved": true}',
        "macro_analyst_json": '{"regime": "RISK_ON"}',
        "coordinator_json": '{"action": "BUY"}',
    }
    defaults.update(overrides)
    return TradeOutcome(**defaults)


def _classifier() -> MistakeClassifierAgent:
    return MistakeClassifierAgent(api_key="test-key")


def test_valid_payload_passes() -> None:
    agent = _classifier()
    agent._validate_payload(
        {
            "primary_category": "signal_wrong",
            "secondary_categories": ["market_regime_changed"],
            "what_went_wrong": "breakout failed",
            "what_we_should_have_seen": "macro regime was shifting",
            "confidence_in_diagnosis": 0.7,
        }
    )


def test_invalid_primary_category() -> None:
    agent = _classifier()
    with pytest.raises(AgentExecutionError, match="primary_category"):
        agent._validate_payload(
            {
                "primary_category": "made_up",
                "secondary_categories": [],
                "what_went_wrong": "x",
                "what_we_should_have_seen": "y",
                "confidence_in_diagnosis": 0.5,
            }
        )


def test_invalid_secondary_category() -> None:
    agent = _classifier()
    with pytest.raises(AgentExecutionError, match="secondary_category"):
        agent._validate_payload(
            {
                "primary_category": "signal_wrong",
                "secondary_categories": ["weird_one"],
                "what_went_wrong": "x",
                "what_we_should_have_seen": "y",
                "confidence_in_diagnosis": 0.5,
            }
        )


def test_secondary_must_be_list() -> None:
    agent = _classifier()
    with pytest.raises(AgentExecutionError, match="must be list"):
        agent._validate_payload(
            {
                "primary_category": "signal_wrong",
                "secondary_categories": "not_a_list",
                "what_went_wrong": "x",
                "what_we_should_have_seen": "y",
                "confidence_in_diagnosis": 0.5,
            }
        )


def test_confidence_must_be_number() -> None:
    agent = _classifier()
    with pytest.raises(AgentExecutionError, match="must be number"):
        agent._validate_payload(
            {
                "primary_category": "signal_wrong",
                "secondary_categories": [],
                "what_went_wrong": "x",
                "what_we_should_have_seen": "y",
                "confidence_in_diagnosis": "high",
            }
        )


def test_confidence_out_of_range() -> None:
    agent = _classifier()
    with pytest.raises(AgentExecutionError, match=r"\[0, 1\]"):
        agent._validate_payload(
            {
                "primary_category": "signal_wrong",
                "secondary_categories": [],
                "what_went_wrong": "x",
                "what_we_should_have_seen": "y",
                "confidence_in_diagnosis": 1.5,
            }
        )


def test_missing_required_key() -> None:
    agent = _classifier()
    with pytest.raises(AgentExecutionError):
        agent._validate_payload(
            {
                "primary_category": "signal_wrong",
                "secondary_categories": [],
                "what_went_wrong": "x",
                "confidence_in_diagnosis": 0.5,
                # missing: what_we_should_have_seen
            }
        )


def test_trade_outcome_to_context_full() -> None:
    outcome = _make_closed_outcome()
    ctx = trade_outcome_to_context(outcome)
    assert ctx["trade_id"] == "t1"
    assert ctx["symbol"] == "BTC-USDT"
    assert ctx["side"] == "BUY"
    assert ctx["entry_price"] == "80500"
    assert ctx["pnl_pct"] == "-0.62"
    assert ctx["exit_reason"] == "SL"
    assert ctx["signal_json"] == '{"action": "BUY"}'
    assert ctx["coordinator_json"] == '{"action": "BUY"}'


def test_trade_outcome_to_context_rejects_open() -> None:
    outcome = TradeOutcome(
        trade_id="t1",
        symbol="BTC-USDT",
        side="BUY",
        entry_time_ms=1_700_000_000_000,
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        signal_candidate_json="{}",
        market_analyst_json="{}",
        sentiment_analyst_json="{}",
        risk_overseer_json="{}",
        macro_analyst_json="{}",
        coordinator_json="{}",
    )
    with pytest.raises(ValueError, match="ещё открыт"):
        trade_outcome_to_context(outcome)


def test_all_10_categories_accepted() -> None:
    """Все 10 категорий из плана #18 должны валидироваться."""
    agent = _classifier()
    categories = [
        "signal_wrong",
        "sentiment_wrong",
        "market_regime_changed",
        "slippage_high",
        "risk_overlooked",
        "execution_late",
        "tp_too_aggressive",
        "sl_too_tight",
        "correlation_overlooked",
        "macro_event_missed",
    ]
    for cat in categories:
        agent._validate_payload(
            {
                "primary_category": cat,
                "secondary_categories": [],
                "what_went_wrong": "x",
                "what_we_should_have_seen": "y",
                "confidence_in_diagnosis": 0.5,
            }
        )


def test_confidence_zero_and_one_accepted() -> None:
    agent = _classifier()
    for conf in (0.0, 1.0):
        agent._validate_payload(
            {
                "primary_category": "signal_wrong",
                "secondary_categories": [],
                "what_went_wrong": "x",
                "what_we_should_have_seen": "y",
                "confidence_in_diagnosis": conf,
            }
        )
