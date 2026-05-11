"""Unit-тесты ``adapters.bingx.journal.OrderJournal``."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from adapters.bingx.journal import OrderJournal
from adapters.bingx.private_models import OrderAck, OrderRequest, OrderUpdateEvent


def _make_req() -> OrderRequest:
    return OrderRequest(
        symbol="BTC-USDT",
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("0.001"),
        attached_stop_loss=Decimal("60000"),
    )


def _make_ack(status: str = "NEW") -> OrderAck:
    return OrderAck.model_validate(
        {
            "orderId": "999",
            "clientOrderID": "test-coid-1",
            "symbol": "BTC-USDT",
            "side": "BUY",
            "positionSide": "BOTH",
            "type": "MARKET",
            "status": status,
            "price": "0",
            "origQty": "0.001",
            "executedQty": "0",
            "avgPrice": "62000",
            "stopLoss": (
                '{"type":"STOP_MARKET","stopPrice":60000,"workingType":"MARK_PRICE"}'
            ),
            "takeProfit": "",
            "time": 1_700_000_000_000,
            "updateTime": 1_700_000_000_500,
            "reduceOnly": False,
        }
    )


@pytest.fixture
def journal(tmp_path: Path) -> OrderJournal:
    return OrderJournal(tmp_path / "orders.db")


@pytest.mark.asyncio
async def test_journal_records_pending_then_ack(journal: OrderJournal) -> None:
    req = _make_req()
    await journal.record_pending(req, "test-coid-1")
    entry = await journal.get("test-coid-1")
    assert entry is not None
    assert entry.status == "pending"
    assert entry.symbol == "BTC-USDT"
    assert entry.attached_sl == Decimal("60000")

    await journal.record_ack("test-coid-1", _make_ack("NEW"))
    entry = await journal.get("test-coid-1")
    assert entry is not None
    assert entry.status == "acked"
    assert entry.exchange_order_id == "999"
    assert entry.ack_payload is not None


@pytest.mark.asyncio
async def test_journal_records_failure(journal: OrderJournal) -> None:
    req = _make_req()
    await journal.record_pending(req, "test-coid-2")
    await journal.record_failure("test-coid-2", "compensating_close: SL missing")
    entry = await journal.get("test-coid-2")
    assert entry is not None
    assert entry.status == "failed"
    assert entry.failure_reason is not None
    assert "SL missing" in entry.failure_reason


@pytest.mark.asyncio
async def test_journal_updates_from_order_event(journal: OrderJournal) -> None:
    req = _make_req()
    await journal.record_pending(req, "test-coid-3")
    await journal.record_ack("test-coid-3", _make_ack("NEW"))

    event = OrderUpdateEvent.model_validate(
        {
            "e": "ORDER_TRADE_UPDATE",
            "E": 1_700_000_001_000,
            "symbol": "BTC-USDT",
            "order_id": "999",
            "client_order_id": "test-coid-3",
            "side": "BUY",
            "type": "MARKET",
            "status": "FILLED",
            "position_side": "BOTH",
            "price": "0",
            "original_quantity": "0.001",
            "executed_quantity": "0.001",
            "average_price": "62000",
            "execution_type": "TRADE",
        }
    )
    await journal.update_from_event(event)
    entry = await journal.get("test-coid-3")
    assert entry is not None
    assert entry.status == "filled"
    assert entry.last_event_type == "TRADE"


@pytest.mark.asyncio
async def test_journal_list_pending_filters_by_status_and_symbol(
    journal: OrderJournal,
) -> None:
    # 2 pending по BTC, 1 filled по ETH-USDT.
    req_btc = _make_req()
    await journal.record_pending(req_btc, "a")
    await journal.record_pending(req_btc, "b")

    req_eth = OrderRequest(
        symbol="ETH-USDT",
        side="BUY",
        order_type="MARKET",
        quantity=Decimal("0.01"),
        attached_stop_loss=Decimal("3000"),
    )
    await journal.record_pending(req_eth, "c")
    eth_ack = _make_ack("FILLED")
    await journal.record_ack("c", eth_ack)

    btc_pending = await journal.list_pending("BTC-USDT")
    assert {e.client_order_id for e in btc_pending} == {"a", "b"}
    all_pending = await journal.list_pending()
    # 'c' стал filled → не в pending списке.
    assert "c" not in {e.client_order_id for e in all_pending}
