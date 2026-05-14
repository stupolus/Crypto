"""Unit-тесты ``TradeOutcome`` / ``ExitData`` / ``DecisionContext``."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from core.postmortem.models import DecisionContext, ExitData, TradeOutcome


def _make_open_trade(**overrides: object) -> TradeOutcome:
    defaults: dict[str, object] = {
        "trade_id": "t1",
        "symbol": "BTC-USDT",
        "side": "BUY",
        "entry_time_ms": 1_700_000_000_000,
        "entry_price": Decimal("80500"),
        "size": Decimal("0.1"),
        "signal_candidate_json": "{}",
        "market_analyst_json": "{}",
        "sentiment_analyst_json": "{}",
        "risk_overseer_json": "{}",
        "macro_analyst_json": "{}",
        "coordinator_json": "{}",
    }
    defaults.update(overrides)
    return TradeOutcome(**defaults)


def test_open_trade_is_not_closed() -> None:
    t = _make_open_trade()
    assert t.is_closed is False
    assert t.is_loss is False
    assert t.is_win is False


def test_closed_winning_trade() -> None:
    t = _make_open_trade(
        exit_time_ms=1_700_000_900_000,
        exit_price=Decimal("82000"),
        pnl_usd=Decimal("150"),
        pnl_pct=Decimal("1.86"),
        exit_reason="TP1",
        holding_time_min=15,
    )
    assert t.is_closed is True
    assert t.is_win is True
    assert t.is_loss is False


def test_closed_losing_trade() -> None:
    t = _make_open_trade(
        exit_time_ms=1_700_000_900_000,
        exit_price=Decimal("80000"),
        pnl_usd=Decimal("-50"),
        pnl_pct=Decimal("-0.62"),
        exit_reason="SL",
        holding_time_min=15,
    )
    assert t.is_closed is True
    assert t.is_win is False
    assert t.is_loss is True


def test_mixed_exit_state_rejected() -> None:
    """exit_time без exit_price → ValidationError."""
    with pytest.raises(ValidationError, match="exit_time_ms и exit_price"):
        _make_open_trade(exit_time_ms=1_700_000_900_000)


def test_exit_before_entry_rejected() -> None:
    with pytest.raises(ValidationError, match="exit_time_ms"):
        _make_open_trade(
            exit_time_ms=1_600_000_000_000,
            exit_price=Decimal("80000"),
            exit_reason="SL",
            holding_time_min=0,
            pnl_usd=Decimal("0"),
            pnl_pct=Decimal("0"),
        )


def test_entry_price_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _make_open_trade(entry_price=Decimal("0"))


def test_size_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        _make_open_trade(size=Decimal("0"))


def test_invalid_exit_reason_rejected() -> None:
    with pytest.raises(ValidationError):
        _make_open_trade(
            exit_time_ms=1_700_000_900_000,
            exit_price=Decimal("80000"),
            exit_reason="WRONG",
            holding_time_min=10,
            pnl_usd=Decimal("0"),
            pnl_pct=Decimal("0"),
        )


def test_frozen_model() -> None:
    t = _make_open_trade()
    with pytest.raises(ValidationError):
        t.trade_id = "t2"  # type: ignore[misc]


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        _make_open_trade(unknown_field="x")


def test_exit_data_construction() -> None:
    ed = ExitData(
        exit_time_ms=1_700_000_900_000,
        exit_price=Decimal("82000"),
        pnl_usd=Decimal("150"),
        pnl_pct=Decimal("1.86"),
        exit_reason="TP1",
        holding_time_min=15,
        slippage_bps=Decimal("2.5"),
    )
    assert ed.exit_reason == "TP1"
    assert ed.slippage_bps == Decimal("2.5")


def test_decision_context_construction() -> None:
    ctx = DecisionContext(
        trade_id="t1",
        symbol="BTC-USDT",
        side="BUY",
        entry_time_ms=1_700_000_000_000,
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        signal_candidate={"action": "BUY"},
        market_analyst={"state": "TRENDING_UP"},
        sentiment_analyst={"sentiment_score": 0.4},
        risk_overseer={"approved": True},
        macro_analyst={"regime": "RISK_ON"},
        coordinator={"action": "BUY"},
        latency_decision_ms=350,
    )
    assert ctx.signal_candidate["action"] == "BUY"
    assert ctx.latency_decision_ms == 350


def test_decision_context_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        DecisionContext(
            trade_id="t1",
            symbol="BTC-USDT",
            side="BUY",
            entry_time_ms=1,
            entry_price=Decimal("1"),
            size=Decimal("1"),
            signal_candidate={},
            market_analyst={},
            sentiment_analyst={},
            risk_overseer={},
            macro_analyst={},
            coordinator={},
            extra_field="boom",  # type: ignore[call-arg]
        )
