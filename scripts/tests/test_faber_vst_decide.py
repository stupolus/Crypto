"""Тест критического пути faber_vst_executor.decide (без сети)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from scripts import faber_vst_executor
from scripts.faber_vst_executor import decide, is_halted, period_keys, roll_state


def test_cash_flat_noop() -> None:
    assert decide("CASH", Decimal("0"), Decimal("0")) == "noop"


def test_cash_with_position_closes() -> None:
    assert decide("CASH", Decimal("5"), Decimal("0")) == "close"


def test_long_from_flat_opens() -> None:
    assert decide("LONG", Decimal("0"), Decimal("3")) == "open_long"
    assert decide("LONG", Decimal("-2"), Decimal("3")) == "open_long"


def test_long_within_tolerance_noop() -> None:
    # |3.1 - 3| / 3 = 3.3% < 15% → уже в target
    assert decide("LONG", Decimal("3.1"), Decimal("3")) == "noop"


def test_long_out_of_tolerance_rebalance() -> None:
    # |6 - 3| / 3 = 100% → ребаланс
    assert decide("LONG", Decimal("6"), Decimal("3")) == "rebalance"


def test_kill_switch(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    halt = tmp_path / "faber_HALT"
    monkeypatch.setattr(faber_vst_executor, "_HALT", halt)
    assert is_halted() is False
    halt.write_text("stop")
    assert is_halted() is True


def test_period_keys() -> None:
    d, w, m = period_keys(datetime(2026, 5, 18, tzinfo=UTC))
    assert d == "2026-05-18"
    assert w.startswith("2026-W")
    assert m == "2026-05"


def test_roll_state_new_day_resets() -> None:
    prev = {
        "day": "2026-05-17",
        "day_start_equity": "100",
        "day_trades": "3",
        "consecutive_losses": "2",
        "week": "2026-W20",
        "week_start_equity": "100",
        "month": "2026-05",
        "month_start_equity": "100",
    }
    st, dp, wp, mp = roll_state(prev, Decimal("90"), ("2026-05-18", "2026-W20", "2026-05"))
    assert st["day_trades"] == "0"  # новый день — сброс
    assert st["consecutive_losses"] == "0"
    assert dp == Decimal("0")  # day_start переставлен на текущую
    assert wp == Decimal("-10")  # неделя та же → pnl от старого старта
    assert mp == Decimal("-10")


def test_roll_state_same_day_keeps() -> None:
    prev = {
        "day": "2026-05-18",
        "day_start_equity": "100",
        "day_trades": "1",
        "consecutive_losses": "1",
        "week": "2026-W20",
        "week_start_equity": "100",
        "month": "2026-05",
        "month_start_equity": "100",
    }
    st, dp, _wp, _mp = roll_state(prev, Decimal("97"), ("2026-05-18", "2026-W20", "2026-05"))
    assert st["day_trades"] == "1"  # тот же день — не сброшено
    assert dp == Decimal("-3")
