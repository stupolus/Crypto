"""Unit-тесты ``ExitTracker``."""

from __future__ import annotations

from decimal import Decimal

from adapters.bingx.private_models import OrderUpdateEvent
from core.postmortem.exit_tracker import ExitTracker


def _make_event(
    *,
    symbol: str = "BTC-USDT",
    side: str = "SELL",
    order_type: str = "STOP_MARKET",
    status: str = "FILLED",
    execution_type: str = "TRADE",
    order_id: str = "exit_42",
    price: str = "79800",
    average_price: str | None = "79800",
    executed_qty: str = "0.1",
    event_time_ms: int = 1_700_000_900_000,
    realised_profit: str | None = "-70",
) -> OrderUpdateEvent:
    return OrderUpdateEvent.model_validate(
        {
            "e": "ORDER_TRADE_UPDATE",
            "E": event_time_ms,
            "symbol": symbol,
            "order_id": order_id,
            "side": side,
            "type": order_type,
            "status": status,
            "position_side": "BOTH",
            "price": price,
            "original_quantity": "0.1",
            "executed_quantity": executed_qty,
            "average_price": average_price,
            "execution_type": execution_type,
            "realised_profit": realised_profit,
        }
    )


def test_register_entry_creates_open_trade() -> None:
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="t1",
        symbol="BTC-USDT",
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )
    assert tracker.open_count == 1
    assert tracker.has_open("BTC-USDT")
    assert not tracker.has_open("ETH-USDT")


def test_observe_stop_loss_fill_returns_exit_data() -> None:
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="t1",
        symbol="BTC-USDT",
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )
    result = tracker.observe_order_event(_make_event(order_type="STOP_MARKET"))
    assert result is not None
    trade_id, exit_data = result
    assert trade_id == "t1"
    assert exit_data.exit_reason == "SL"
    assert exit_data.exit_price == Decimal("79800")
    assert exit_data.holding_time_min == 15  # 900_000 ms = 15 min
    assert exit_data.pnl_usd == Decimal("-70")
    # PnL pct: (79800 - 80500) / 80500 * 100 ≈ -0.870
    assert exit_data.pnl_pct == Decimal("-0.870")
    # Closed → no longer open
    assert tracker.open_count == 0


def test_observe_take_profit_fill_returns_tp1() -> None:
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="t1",
        symbol="BTC-USDT",
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )
    result = tracker.observe_order_event(
        _make_event(
            order_type="TAKE_PROFIT_MARKET",
            average_price="82000",
            realised_profit="150",
        )
    )
    assert result is not None
    _, exit_data = result
    assert exit_data.exit_reason == "TP1"
    assert exit_data.exit_price == Decimal("82000")
    assert exit_data.pnl_usd == Decimal("150")


def test_observe_partial_status_returns_none() -> None:
    """PARTIALLY_FILLED не закрывает — только FILLED."""
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="t1",
        symbol="BTC-USDT",
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )
    result = tracker.observe_order_event(_make_event(status="PARTIALLY_FILLED"))
    assert result is None
    assert tracker.open_count == 1  # still open


def test_observe_entry_fill_returns_none() -> None:
    """LIMIT fill = entry, не close → не возвращаем ExitData."""
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="t1",
        symbol="BTC-USDT",
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )
    result = tracker.observe_order_event(_make_event(order_type="LIMIT"))
    assert result is None
    assert tracker.open_count == 1


def test_observe_no_open_trade_returns_none() -> None:
    tracker = ExitTracker()
    # Никаких registered entries
    result = tracker.observe_order_event(_make_event())
    assert result is None


def test_observe_zero_executed_qty_returns_none() -> None:
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="t1",
        symbol="BTC-USDT",
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )
    result = tracker.observe_order_event(_make_event(executed_qty="0"))
    assert result is None
    assert tracker.open_count == 1


def test_observe_missing_realised_profit_uses_zero() -> None:
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="t1",
        symbol="BTC-USDT",
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )
    result = tracker.observe_order_event(_make_event(realised_profit=None))
    assert result is not None
    _, exit_data = result
    assert exit_data.pnl_usd == Decimal("0")


def test_observe_falls_back_to_price_when_no_average() -> None:
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="t1",
        symbol="BTC-USDT",
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )
    result = tracker.observe_order_event(_make_event(average_price=None, price="79750"))
    assert result is not None
    _, exit_data = result
    assert exit_data.exit_price == Decimal("79750")


def test_register_entry_overwrites_existing() -> None:
    """Повторный register_entry на тот же символ overwrite'нет (с warning)."""
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="t1",
        symbol="BTC-USDT",
        entry_price=Decimal("80000"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )
    tracker.register_entry(
        trade_id="t2",
        symbol="BTC-USDT",
        entry_price=Decimal("81000"),
        size=Decimal("0.05"),
        entry_time_ms=1_700_000_500_000,
    )
    assert tracker.open_count == 1
    # Close → возвращает t2 trade_id
    result = tracker.observe_order_event(_make_event(order_type="STOP_MARKET"))
    assert result is not None
    trade_id, _ = result
    assert trade_id == "t2"


def test_close_unfilled_removes_open() -> None:
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="t1",
        symbol="BTC-USDT",
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )
    trade_id = tracker.close_unfilled("BTC-USDT")
    assert trade_id == "t1"
    assert tracker.open_count == 0


def test_close_unfilled_no_open_returns_none() -> None:
    tracker = ExitTracker()
    assert tracker.close_unfilled("BTC-USDT") is None


def test_multiple_symbols_independent() -> None:
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="t1",
        symbol="BTC-USDT",
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )
    tracker.register_entry(
        trade_id="t2",
        symbol="ETH-USDT",
        entry_price=Decimal("3200"),
        size=Decimal("1.0"),
        entry_time_ms=1_700_000_000_000,
    )
    assert tracker.open_count == 2
    # Закрытие BTC не трогает ETH
    result = tracker.observe_order_event(_make_event(symbol="BTC-USDT"))
    assert result is not None
    assert tracker.open_count == 1
    assert tracker.has_open("ETH-USDT")
