"""Тесты доменных моделей, в первую очередь инвариантов OrderRequest."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from exchanges.models import (
    OHLCV,
    Balance,
    MarginMode,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    Ticker,
)


def test_ohlcv_construct() -> None:
    c = OHLCV(
        timestamp=1,
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal("1.5"),
        volume=Decimal("100"),
    )
    assert c.high == Decimal("2")


def test_ticker_spread() -> None:
    t = Ticker(
        symbol="BTC/USDT:USDT",
        last=Decimal("100"),
        bid=Decimal("99"),
        ask=Decimal("101"),
        quote_volume_24h=Decimal("1000000"),
        timestamp=1,
    )
    assert t.spread == Decimal("2")
    assert t.spread_pct == Decimal("2") / Decimal("100")


def test_ticker_spread_pct_zero_mid() -> None:
    t = Ticker(
        symbol="X",
        last=Decimal("0"),
        bid=Decimal("0"),
        ask=Decimal("0"),
        quote_volume_24h=Decimal("0"),
        timestamp=1,
    )
    assert t.spread_pct == Decimal(0)


def test_balance_and_position_construct() -> None:
    b = Balance(asset="USDT", free=Decimal("100"), used=Decimal("0"), total=Decimal("100"))
    assert b.total == Decimal("100")
    p = Position(
        symbol="BTC/USDT:USDT",
        side=PositionSide.LONG,
        size=Decimal("0.1"),
        entry_price=Decimal("100"),
        mark_price=Decimal("101"),
        leverage=Decimal("3"),
        margin_mode=MarginMode.ISOLATED,
        unrealized_pnl=Decimal("0.1"),
    )
    assert p.liquidation_price is None


def test_valid_market_order_with_stop() -> None:
    req = OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
        stop_price=Decimal("95"),
    )
    assert req.margin_mode is MarginMode.ISOLATED
    assert req.stop_price == Decimal("95")


def test_valid_limit_buy() -> None:
    req = OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("0.1"),
        price=Decimal("100"),
        stop_price=Decimal("95"),
    )
    assert req.price == Decimal("100")


def test_stop_price_is_required() -> None:
    with pytest.raises(ValidationError):
        OrderRequest(  # type: ignore[call-arg]
            symbol="BTC/USDT:USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
        )


def test_stop_price_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="BTC/USDT:USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            stop_price=Decimal("0"),
        )


def test_quantity_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="BTC/USDT:USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0"),
            stop_price=Decimal("95"),
        )


def test_cross_margin_rejected() -> None:
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="BTC/USDT:USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            stop_price=Decimal("95"),
            margin_mode=MarginMode.CROSS,
        )


def test_limit_requires_price() -> None:
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="BTC/USDT:USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            stop_price=Decimal("95"),
        )


def test_market_rejects_price() -> None:
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="BTC/USDT:USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("0.1"),
            stop_price=Decimal("95"),
            price=Decimal("100"),
        )


def test_buy_stop_must_be_below_entry() -> None:
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="BTC/USDT:USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("100"),
            stop_price=Decimal("101"),  # выше входа — недопустимо для BUY
        )


def test_sell_stop_must_be_above_entry() -> None:
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="BTC/USDT:USDT",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal("0.1"),
            price=Decimal("100"),
            stop_price=Decimal("99"),  # ниже входа — недопустимо для SELL
        )


def test_order_request_is_frozen() -> None:
    req = OrderRequest(
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("0.1"),
        stop_price=Decimal("95"),
    )
    with pytest.raises(ValidationError):
        req.quantity = Decimal("1")  # type: ignore[misc]


def test_order_result_defaults() -> None:
    r = OrderResult(order_id="1", symbol="BTC/USDT:USDT", status=OrderStatus.OPEN)
    assert r.filled_quantity == Decimal(0)
    assert r.average_price is None
