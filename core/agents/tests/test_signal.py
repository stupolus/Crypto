"""Unit-тесты ``SignalCandidate``."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.agents import SignalCandidate


def test_signal_candidate_basic() -> None:
    s = SignalCandidate(
        symbol="BTC-USDT",
        action="BUY",
        timestamp_ms=1_700_000_000_000,
        strategy_name="btc_breakout",
    )
    assert s.symbol == "BTC-USDT"
    assert s.action == "BUY"
    assert s.confidence_raw == 0.5
    assert s.indicators == {}
    assert s.proposed_entry is None


def test_signal_candidate_with_full_proposal() -> None:
    s = SignalCandidate(
        symbol="ETH-USDT",
        action="SELL",
        timestamp_ms=1_700_000_000_000,
        strategy_name="us_session_breakout",
        confidence_raw=0.7,
        indicators={"atr": "12.3", "donchian_low": "2270"},
        proposed_entry=Decimal("2280"),
        proposed_sl=Decimal("2295"),
        proposed_tp=(Decimal("2255"), Decimal("2230")),
    )
    assert s.proposed_entry == Decimal("2280")
    assert s.proposed_tp == (Decimal("2255"), Decimal("2230"))


def test_signal_candidate_immutable() -> None:
    from dataclasses import FrozenInstanceError

    s = SignalCandidate(
        symbol="BTC-USDT",
        action="BUY",
        timestamp_ms=1_700_000_000_000,
        strategy_name="btc_breakout",
    )
    with pytest.raises(FrozenInstanceError):
        s.symbol = "ETH-USDT"  # type: ignore[misc]


def test_to_context_serialization() -> None:
    s = SignalCandidate(
        symbol="BTC-USDT",
        action="BUY",
        timestamp_ms=1_700_000_000_000,
        strategy_name="btc_breakout",
        confidence_raw=0.8,
        indicators={"atr": "100"},
        proposed_entry=Decimal("80500"),
        proposed_sl=Decimal("79800"),
        proposed_tp=(Decimal("81500"),),
    )
    ctx = s.to_context()
    assert ctx["symbol"] == "BTC-USDT"
    assert ctx["proposed_entry"] == "80500"
    assert ctx["proposed_sl"] == "79800"
    assert ctx["proposed_tp"] == ["81500"]
    assert ctx["indicators"] == {"atr": "100"}


def test_to_context_with_none_values() -> None:
    """Если цены не предложены — None в выводе (не строка 'None')."""
    s = SignalCandidate(
        symbol="BTC-USDT",
        action="BUY",
        timestamp_ms=1_700_000_000_000,
        strategy_name="btc_breakout",
    )
    ctx = s.to_context()
    assert ctx["proposed_entry"] is None
    assert ctx["proposed_sl"] is None
    assert ctx["proposed_tp"] == []
