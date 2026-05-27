"""Unit-тесты ``build_signal_candidate``."""

from __future__ import annotations

from decimal import Decimal

from adapters.bingx.private_models import OrderRequest
from core.agents import build_signal_candidate


def _make_order_request(
    side: str = "BUY",
    price: Decimal | None = Decimal("80500"),
    stop_loss: Decimal | None = Decimal("79800"),
    take_profit: Decimal | None = None,
    quantity: Decimal = Decimal("0.001"),
) -> OrderRequest:
    return OrderRequest(
        symbol="BTC-USDT",
        side=side,
        position_side="LONG" if side == "BUY" else "SHORT",
        order_type="LIMIT",
        quantity=quantity,
        price=price,
        attached_stop_loss=stop_loss,
        attached_take_profit=take_profit,
    )


def test_build_signal_candidate_basic() -> None:
    req = _make_order_request(
        side="BUY",
        price=Decimal("80500"),
        stop_loss=Decimal("79800"),
    )
    signal = build_signal_candidate(
        req,
        strategy_name="btc_breakout",
        timestamp_ms=1_700_000_000_000,
    )
    assert signal.symbol == "BTC-USDT"
    assert signal.action == "BUY"
    assert signal.strategy_name == "btc_breakout"
    assert signal.timestamp_ms == 1_700_000_000_000
    assert signal.proposed_entry == Decimal("80500")
    assert signal.proposed_sl == Decimal("79800")
    assert signal.proposed_tp == ()


def test_build_signal_candidate_with_tp() -> None:
    req = _make_order_request(
        side="SELL",
        price=Decimal("2280"),
        stop_loss=Decimal("2295"),
        take_profit=Decimal("2250"),
    )
    signal = build_signal_candidate(
        req,
        strategy_name="us_session_breakout",
        timestamp_ms=1_700_000_000_000,
    )
    assert signal.action == "SELL"
    assert signal.proposed_tp == (Decimal("2250"),)


def test_build_signal_candidate_with_indicators() -> None:
    req = _make_order_request()
    signal = build_signal_candidate(
        req,
        strategy_name="btc_breakout",
        timestamp_ms=1_700_000_000_000,
        indicators={"atr": "100.5", "donchian_high": "80929", "ema20": "80700"},
        confidence_raw=0.75,
    )
    assert signal.confidence_raw == 0.75
    assert signal.indicators["atr"] == "100.5"
    assert signal.indicators["donchian_high"] == "80929"


def test_build_signal_candidate_default_confidence() -> None:
    req = _make_order_request()
    signal = build_signal_candidate(
        req,
        strategy_name="btc_breakout",
        timestamp_ms=1_700_000_000_000,
    )
    assert signal.confidence_raw == 0.5
    assert signal.indicators == {}


def test_build_signal_candidate_default_empty_tp() -> None:
    """OrderRequest без attached_take_profit → proposed_tp пустой."""
    req = _make_order_request(take_profit=None)
    signal = build_signal_candidate(
        req,
        strategy_name="btc_breakout",
        timestamp_ms=1_700_000_000_000,
    )
    assert signal.proposed_tp == ()


def test_build_signal_candidate_market_order_no_entry_price() -> None:
    """MARKET ордер без price → proposed_entry None."""
    req = OrderRequest(
        symbol="BTC-USDT",
        side="BUY",
        position_side="LONG",
        order_type="MARKET",
        quantity=Decimal("0.001"),
        attached_stop_loss=Decimal("79800"),
    )
    signal = build_signal_candidate(
        req,
        strategy_name="btc_breakout",
        timestamp_ms=1_700_000_000_000,
    )
    assert signal.proposed_entry is None
    assert signal.proposed_sl == Decimal("79800")
