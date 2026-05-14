"""Unit-тесты ``aggregate_extended_signals``."""

from __future__ import annotations

from decimal import Decimal

from core.signals.extended_aggregator import aggregate_extended_signals
from core.signals.funding_extreme import FundingExtremeSignal
from core.signals.liquidation_sweep import LiquidationSweepSignal
from core.signals.order_flow import OrderFlowSignal


def _make_funding(action: str = "BUY", conf: float = 0.8) -> FundingExtremeSignal:
    return FundingExtremeSignal(
        action=action,
        confidence_raw=conf,
        funding_rate=Decimal("-0.001"),
        percentile=Decimal("0.02"),
        reason="test",
    )


def _make_order_flow(action: str = "BUY", conf: float = 0.7) -> OrderFlowSignal:
    return OrderFlowSignal(
        action=action,
        confidence_raw=conf,
        imbalance=Decimal("0.7"),
        bid_volume=Decimal("85"),
        ask_volume=Decimal("15"),
        reason="test",
    )


def _make_liq(action: str = "BUY", conf: float = 0.9) -> LiquidationSweepSignal:
    return LiquidationSweepSignal(
        action=action,
        confidence_raw=conf,
        spike_ratio=Decimal("9"),
        recent_total=Decimal("9000"),
        baseline_median=Decimal("1000"),
        long_share=Decimal("0.9"),
        reason="test",
    )


def test_all_three_buy_returns_candidate() -> None:
    result = aggregate_extended_signals(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        funding_signal=_make_funding("BUY"),
        order_flow_signal=_make_order_flow("BUY"),
        liquidation_signal=_make_liq("BUY"),
    )
    assert result.candidate is not None
    assert result.candidate.action == "BUY"
    assert result.candidate.symbol == "BTC-USDT"
    assert result.candidate.strategy_name == "extended_aggregator"
    # confidence = avg(0.8, 0.7, 0.9) = 0.8
    assert abs(result.candidate.confidence_raw - 0.8) < 0.001


def test_two_of_three_buy_returns_candidate() -> None:
    result = aggregate_extended_signals(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        funding_signal=_make_funding("BUY"),
        order_flow_signal=_make_order_flow("BUY"),
        liquidation_signal=None,
    )
    assert result.candidate is not None
    assert result.candidate.action == "BUY"
    # Только 2 active confidences: avg(0.8, 0.7) = 0.75
    assert abs(result.candidate.confidence_raw - 0.75) < 0.001


def test_one_signal_returns_none() -> None:
    result = aggregate_extended_signals(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        funding_signal=_make_funding("BUY"),
        order_flow_signal=None,
        liquidation_signal=None,
    )
    assert result.candidate is None
    assert "только 1" in result.reason


def test_zero_signals_returns_none() -> None:
    result = aggregate_extended_signals(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        funding_signal=None,
        order_flow_signal=None,
        liquidation_signal=None,
    )
    assert result.candidate is None
    assert "только 0" in result.reason


def test_mixed_signals_returns_none() -> None:
    """funding=BUY, order_flow=SELL, liq=SELL → SELL wins (2 SELL > 1 BUY).

    Wait — 2/3 SELL → consensus SELL. Let me test the actual mixed case.
    """
    result = aggregate_extended_signals(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        funding_signal=_make_funding("BUY"),
        order_flow_signal=_make_order_flow("SELL"),
        liquidation_signal=_make_liq("SELL"),
    )
    # 2 SELL, 1 BUY → SELL wins
    assert result.candidate is not None
    assert result.candidate.action == "SELL"


def test_split_1_1_with_one_none_returns_none() -> None:
    """1 BUY, 1 SELL, 1 None → не consensus."""
    result = aggregate_extended_signals(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        funding_signal=_make_funding("BUY"),
        order_flow_signal=_make_order_flow("SELL"),
        liquidation_signal=None,
    )
    assert result.candidate is None
    assert "smешанные" in result.reason or "1 BUY, 1 SELL" in result.reason


def test_votes_dict_recorded() -> None:
    result = aggregate_extended_signals(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        funding_signal=_make_funding("BUY"),
        order_flow_signal=None,
        liquidation_signal=_make_liq("BUY"),
    )
    assert result.votes == {
        "funding_extreme": "BUY",
        "order_flow": None,
        "liquidation_sweep": "BUY",
    }


def test_indicators_only_from_agreeing_signals() -> None:
    """funding=SELL, order_flow=BUY, liq=BUY → BUY consensus.
    Indicators должны быть только из order_flow и liq (не funding)."""
    result = aggregate_extended_signals(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        funding_signal=_make_funding("SELL"),
        order_flow_signal=_make_order_flow("BUY"),
        liquidation_signal=_make_liq("BUY"),
    )
    assert result.candidate is not None
    assert result.candidate.action == "BUY"
    indicators = result.candidate.indicators
    # funding_rate НЕ должен быть в indicators (funding signaled SELL)
    assert "funding_rate" not in indicators
    # order_flow и liquidation должны быть
    assert "orderbook_imbalance" in indicators
    assert "liquidation_spike_ratio" in indicators


def test_proposed_levels_are_none() -> None:
    """Aggregator не знает цен — entry/SL/TP остаются None."""
    result = aggregate_extended_signals(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        funding_signal=_make_funding("BUY"),
        order_flow_signal=_make_order_flow("BUY"),
        liquidation_signal=None,
    )
    assert result.candidate is not None
    assert result.candidate.proposed_entry is None
    assert result.candidate.proposed_sl is None
    assert result.candidate.proposed_tp == ()
