"""Unit-тесты ``_user_events_loop_with_tracker`` — Layer 6 capture path.

Используем fake user-stream + spy logger чтобы проверить что
ExitTracker.observe_order_event и TradeOutcomeLogger.record_exit
действительно вызываются на FILLED STOP_MARKET event.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import pytest

from adapters.bingx.private_models import OrderUpdateEvent
from core.postmortem.exit_tracker import ExitTracker
from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import DecisionContext
from runners.live_runner import RunnerState
from runners.llm_runner import _user_events_loop_with_tracker


class _FakeStream:
    """Fake BingXUserDataStream — отдаёт preset events и завершается."""

    def __init__(self, events: list[object]) -> None:
        self._events = events

    async def events(self) -> AsyncIterator[object]:
        for ev in self._events:
            yield ev


class _NoopStrategy:
    def on_fill(self, fill: object) -> None:
        pass


class _NoopJournal:
    async def update_from_event(self, event: object) -> None:
        pass


def _make_order_update(
    *,
    symbol: str = "BTC-USDT",
    order_type: str = "STOP_MARKET",
    status: str = "FILLED",
    order_id: str = "exit_42",
) -> OrderUpdateEvent:
    return OrderUpdateEvent.model_validate(
        {
            "e": "ORDER_TRADE_UPDATE",
            "E": 1_700_000_900_000,
            "symbol": symbol,
            "order_id": order_id,
            "side": "SELL",
            "type": order_type,
            "status": status,
            "position_side": "BOTH",
            "price": "79800",
            "original_quantity": "0.1",
            "executed_quantity": "0.1",
            "average_price": "79800",
            "execution_type": "TRADE",
            "realised_profit": "-70",
        }
    )


def _make_state() -> RunnerState:
    return RunnerState(
        candles_history=[],
        equity=Decimal("1000"),
    )


@pytest.mark.asyncio
async def test_loop_records_exit_on_stop_market_fill(tmp_path: Path) -> None:
    """STOP_MARKET FILLED → ExitTracker matches + record_exit called."""
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    ctx = DecisionContext(
        trade_id="trade_42",
        symbol="BTC-USDT",
        side="BUY",
        entry_time_ms=1_700_000_000_000,
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        signal_candidate={},
        market_analyst={},
        sentiment_analyst={},
        risk_overseer={},
        macro_analyst={},
        coordinator={},
    )
    log.record_entry(ctx)
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="trade_42",
        symbol="BTC-USDT",
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )

    stream = _FakeStream([_make_order_update(order_id="exit_42")])
    await _user_events_loop_with_tracker(
        stream,
        _NoopStrategy(),
        _make_state(),
        _NoopJournal(),
        outcome_logger=log,
        exit_tracker=tracker,
    )

    # Trade закрыт: outcome.is_closed=True
    outcome = log.get_by_id("trade_42")
    assert outcome is not None
    assert outcome.is_closed
    assert outcome.exit_reason == "SL"
    assert outcome.exit_price == Decimal("79800")


@pytest.mark.asyncio
async def test_loop_skips_when_no_tracker(tmp_path: Path) -> None:
    """Если exit_tracker=None → record_exit не вызывается, ошибок нет."""
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    stream = _FakeStream([_make_order_update()])
    await _user_events_loop_with_tracker(
        stream,
        _NoopStrategy(),
        _make_state(),
        _NoopJournal(),
        outcome_logger=log,
        exit_tracker=None,
    )
    # Никаких изменений — БД пустая
    assert list(log.iter_all()) == []


@pytest.mark.asyncio
async def test_loop_handles_no_match(tmp_path: Path) -> None:
    """STOP_MARKET fill но в tracker'е нет open trade → не падает."""
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    tracker = ExitTracker()  # пустой
    stream = _FakeStream([_make_order_update()])
    # Не должно падать
    await _user_events_loop_with_tracker(
        stream,
        _NoopStrategy(),
        _make_state(),
        _NoopJournal(),
        outcome_logger=log,
        exit_tracker=tracker,
    )


@pytest.mark.asyncio
async def test_loop_swallows_handler_error(tmp_path: Path) -> None:
    """Если _handle_user_event падает — loop продолжает, не падает наружу."""
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    tracker = ExitTracker()

    class _RaisingStrategy:
        def on_fill(self, fill: object) -> None:
            raise RuntimeError("boom")

    stream = _FakeStream([_make_order_update()])
    # Должно завершиться чисто (не raise)
    await _user_events_loop_with_tracker(
        stream,
        _RaisingStrategy(),
        _make_state(),
        _NoopJournal(),
        outcome_logger=log,
        exit_tracker=tracker,
    )


@pytest.mark.asyncio
async def test_loop_skips_non_order_event(tmp_path: Path) -> None:
    """AccountUpdateEvent и прочие — не должны триггерить exit_tracker."""
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    tracker = ExitTracker()
    tracker.register_entry(
        trade_id="t1",
        symbol="BTC-USDT",
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        entry_time_ms=1_700_000_000_000,
    )

    # Кастомный event который не OrderUpdateEvent — просто dict
    stream = _FakeStream([{"e": "ACCOUNT_UPDATE", "data": "ignored"}])
    await _user_events_loop_with_tracker(
        stream,
        _NoopStrategy(),
        _make_state(),
        _NoopJournal(),
        outcome_logger=log,
        exit_tracker=tracker,
    )
    # Tracker всё ещё имеет open сделку — не закрылась
    assert tracker.has_open("BTC-USDT")
