"""Тесты SQLite-журнала paper-runner'а."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from exchanges.models import OrderSide
from paper.journal import OpenPositionRecord, PaperJournal, TradeRecord


def _j() -> PaperJournal:
    return PaperJournal(":memory:")


def _trade(ts_close: int, net: str = "10") -> TradeRecord:
    return TradeRecord(
        symbol="BTC/USDT:USDT",
        side=OrderSide.BUY,
        entry_ts=ts_close - 900_000,
        exit_ts=ts_close,
        entry_price=Decimal("100"),
        exit_price=Decimal("110"),
        quantity=Decimal("1"),
        gross_pnl=Decimal(net) + Decimal("1"),
        costs=Decimal("1"),
        net_pnl=Decimal(net),
        exit_reason="tp",
        equity_after=Decimal("10000") + Decimal(net),
    )


def test_set_get_state() -> None:
    j = _j()
    assert j.get_state("k") is None
    j.set_state("k", "v")
    assert j.get_state("k") == "v"
    j.set_state("k", "v2")
    assert j.get_state("k") == "v2"
    j.delete_state("k")
    assert j.get_state("k") is None


def test_last_candle_ts_roundtrip() -> None:
    j = _j()
    assert j.get_last_candle_ts("A/B:B") is None
    j.set_last_candle_ts("A/B:B", 123456789)
    assert j.get_last_candle_ts("A/B:B") == 123456789


def test_open_position_roundtrip() -> None:
    j = _j()
    pos = OpenPositionRecord(
        symbol="X/USDT:USDT",
        side=OrderSide.SELL,
        entry_ts=1_700_000_000_000,
        entry_price=Decimal("200.5"),
        quantity=Decimal("0.5"),
        stop=Decimal("210"),
        take_profit=Decimal("190"),
        entry_cost=Decimal("0.1"),
    )
    j.set_open_position(pos)
    got = j.get_open_position("X/USDT:USDT")
    assert got == pos
    j.delete_open_position("X/USDT:USDT")
    assert j.get_open_position("X/USDT:USDT") is None


def test_equity_roundtrip() -> None:
    j = _j()
    assert j.get_equity() is None
    j.set_equity(Decimal("10000.50"))
    assert j.get_equity() == Decimal("10000.50")


def test_trades_list_all_and_by_day() -> None:
    j = _j()
    # 2026-05-22 UTC
    midnight = int(datetime(2026, 5, 22, 0, 0, 0, tzinfo=UTC).timestamp() * 1000)
    j.append_trade(_trade(midnight + 3_600_000))  # 01:00 UTC 2026-05-22
    j.append_trade(_trade(midnight + 86_400_000 + 3_600_000))  # 01:00 UTC 2026-05-23
    all_t = j.list_trades()
    assert len(all_t) == 2
    today = j.list_trades(day=date(2026, 5, 22))
    assert len(today) == 1
    assert today[0].exit_ts == midnight + 3_600_000


def test_daily_summary_upsert() -> None:
    j = _j()
    d = date(2026, 5, 22)
    j.upsert_daily_summary(
        d,
        trades=3,
        wins=2,
        gross=Decimal("12"),
        costs=Decimal("2"),
        net=Decimal("10"),
        equity_close=Decimal("10010"),
    )
    j.upsert_daily_summary(
        d,
        trades=4,
        wins=3,
        gross=Decimal("15"),
        costs=Decimal("3"),
        net=Decimal("12"),
        equity_close=Decimal("10012"),
    )
    row = j._conn.execute(
        "SELECT trades, wins, net_pnl, equity_close FROM daily_summary WHERE day=?",
        (d.isoformat(),),
    ).fetchone()
    assert row == (4, 3, "12", "10012")


def test_transaction_rollback() -> None:
    j = _j()
    j.set_state("a", "1")
    try:
        with j.transaction():
            j.set_state("a", "2")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert j.get_state("a") == "1"
