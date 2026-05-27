"""Тесты enum-маппинга OrderRequest → Bybit и парсинга Position/Balance."""

from __future__ import annotations

from decimal import Decimal

import pytest

from adapters.bybit.private_models import (
    CoinBalance,
    OrderAck,
    Position,
    idx_to_position_side,
    order_type_to_bybit,
    position_side_to_idx,
    side_to_bybit,
)


def test_side_mapping() -> None:
    assert side_to_bybit("BUY") == "Buy"
    assert side_to_bybit("SELL") == "Sell"
    with pytest.raises(ValueError, match="unknown side"):
        side_to_bybit("HOLD")


def test_position_side_to_idx_mapping() -> None:
    assert position_side_to_idx("LONG") == 1
    assert position_side_to_idx("SHORT") == 2
    assert position_side_to_idx("BOTH") == 0
    with pytest.raises(ValueError, match="unknown position_side"):
        position_side_to_idx("FLAT")


def test_idx_to_position_side_inverse() -> None:
    """Обратная инвариант: round-trip 1→LONG→1, 2→SHORT→2, 0→BOTH→0."""
    for ps in ("LONG", "SHORT", "BOTH"):
        assert idx_to_position_side(position_side_to_idx(ps)) == ps
    with pytest.raises(ValueError):
        idx_to_position_side(99)


def test_order_type_mapping() -> None:
    assert order_type_to_bybit("MARKET") == "Market"
    assert order_type_to_bybit("LIMIT") == "Limit"
    with pytest.raises(ValueError):
        order_type_to_bybit("STOP_LIMIT")


def test_coin_balance_parses_v5_payload() -> None:
    payload = {
        "coin": "USDT",
        "equity": "10000.5",
        "walletBalance": "10000.0",
        "availableToWithdraw": "9500.0",
        "unrealisedPnl": "0.5",
        "cumRealisedPnl": "12.5",
        # лишние поля игнорируются (extra=ignore):
        "borrowAmount": "0",
    }
    b = CoinBalance(**payload)
    assert b.coin == "USDT"
    assert b.equity == Decimal("10000.5")
    assert b.wallet_balance == Decimal("10000.0")
    assert b.available_to_withdraw == Decimal("9500.0")


def test_position_position_amount_signed() -> None:
    """LONG (side=Buy) → положительный signed-размер."""
    long_pos = Position(
        symbol="BTCUSDT",
        side="Buy",
        size=Decimal("0.5"),
        position_idx=1,
        positionValue="15000",
        entryPrice="30000",
        avgPrice="30000",
        leverage="3",
        unrealisedPnl="0",
    )
    assert long_pos.position_amount == Decimal("0.5")


def test_position_short_negative_amount() -> None:
    """SHORT (side=Sell) → отрицательный signed-размер."""
    short_pos = Position(
        symbol="BTCUSDT",
        side="Sell",
        size=Decimal("0.3"),
        position_idx=2,
        entryPrice="30000",
        avgPrice="30000",
    )
    assert short_pos.position_amount == -Decimal("0.3")


def test_position_empty_slot_parses() -> None:
    """Bybit отдаёт пустые слоты в hedge — size=0, side='' допустимо."""
    empty = Position(
        symbol="BTCUSDT",
        side="",
        size=Decimal("0"),
        position_idx=1,
        avgPrice="0",
    )
    assert empty.size == 0


def test_order_ack_minimum_fields() -> None:
    ack = OrderAck(order_id="1234567890", order_link_id="my-coid")
    assert ack.order_id == "1234567890"
    assert ack.order_link_id == "my-coid"
    assert ack.has_attached_stop_loss is True  # см. docstring
