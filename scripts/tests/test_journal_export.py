"""Unit-тесты ``scripts.journal_export``."""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import DecisionContext, ExitData, TradeOutcome
from scripts.journal_export import _row_from_outcome, run, write_csv


def _make_open_outcome(trade_id: str = "open1") -> TradeOutcome:
    return TradeOutcome(
        trade_id=trade_id,
        symbol="BTC-USDT",
        side="BUY",
        entry_time_ms=1_700_000_000_000,
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        signal_candidate_json="{}",
        market_analyst_json="{}",
        sentiment_analyst_json="{}",
        risk_overseer_json="{}",
        macro_analyst_json="{}",
        coordinator_json="{}",
    )


def _make_closed_outcome(trade_id: str = "closed1", is_loss: bool = False) -> TradeOutcome:
    return TradeOutcome(
        trade_id=trade_id,
        symbol="BTC-USDT",
        side="BUY",
        entry_time_ms=1_700_000_000_000,
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        exit_time_ms=1_700_000_900_000,
        exit_price=Decimal("79000") if is_loss else Decimal("82000"),
        pnl_usd=Decimal("-50") if is_loss else Decimal("100"),
        pnl_pct=Decimal("-1.5") if is_loss else Decimal("2.0"),
        exit_reason="SL" if is_loss else "TP1",
        holding_time_min=15,
        signal_candidate_json="{}",
        market_analyst_json="{}",
        sentiment_analyst_json="{}",
        risk_overseer_json="{}",
        macro_analyst_json="{}",
        coordinator_json="{}",
    )


def test_row_from_outcome_open() -> None:
    row = _row_from_outcome(_make_open_outcome())
    assert row["trade_id"] == "open1"
    assert row["exit_time_ms"] == ""
    assert row["exit_price"] == ""
    assert row["is_closed"] is False
    assert row["is_win"] is False


def test_row_from_outcome_winning_closed() -> None:
    row = _row_from_outcome(_make_closed_outcome())
    assert row["exit_time_ms"] == 1_700_000_900_000
    assert row["exit_price"] == "82000"
    assert row["pnl_pct"] == "2.0"
    assert row["exit_reason"] == "TP1"
    assert row["is_closed"] is True
    assert row["is_win"] is True


def test_row_from_outcome_losing_closed() -> None:
    row = _row_from_outcome(_make_closed_outcome("loss1", is_loss=True))
    assert row["is_loss"] is True
    assert row["pnl_pct"] == "-1.5"
    assert row["exit_reason"] == "SL"


def test_write_csv_creates_file_with_header(tmp_path: Path) -> None:
    out = tmp_path / "trades.csv"
    rows = write_csv([_make_closed_outcome(), _make_open_outcome()], out)
    assert rows == 2
    text = out.read_text(encoding="utf-8")
    assert "trade_id" in text
    assert "closed1" in text
    assert "open1" in text


def test_write_csv_filter_only_closed(tmp_path: Path) -> None:
    out = tmp_path / "trades.csv"
    rows = write_csv(
        [
            _make_closed_outcome("c1"),
            _make_open_outcome("o1"),
            _make_closed_outcome("c2", is_loss=True),
        ],
        out,
        only_closed=True,
    )
    assert rows == 2  # o1 пропущен
    text = out.read_text(encoding="utf-8")
    assert "c1" in text
    assert "c2" in text
    assert "o1" not in text


def test_write_csv_creates_parent_dir(tmp_path: Path) -> None:
    deep = tmp_path / "deep" / "nested" / "out.csv"
    rows = write_csv([_make_closed_outcome()], deep)
    assert rows == 1
    assert deep.exists()


def test_write_csv_empty_input(tmp_path: Path) -> None:
    out = tmp_path / "empty.csv"
    rows = write_csv([], out)
    assert rows == 0
    # Header строка осталась
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "trade_id" in lines[0]


def test_csv_format_parseable(tmp_path: Path) -> None:
    """Записанный CSV должен парситься обратно."""
    out = tmp_path / "trades.csv"
    write_csv([_make_closed_outcome(), _make_open_outcome()], out)
    with out.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 2
    # CSV сериализует bool как "True"/"False" строки
    closed_row = next(r for r in rows if r["trade_id"] == "closed1")
    assert closed_row["is_closed"] == "True"
    assert closed_row["exit_reason"] == "TP1"


def test_run_missing_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(tmp_path / "nope.sqlite", tmp_path / "out.csv")
    assert rc == 1
    err = capsys.readouterr().err
    assert "не существует" in err


def test_run_with_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "test.sqlite"
    log = TradeOutcomeLogger(db)
    ctx = DecisionContext(
        trade_id="t1",
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
    log.record_exit(
        "t1",
        ExitData(
            exit_time_ms=1_700_000_900_000,
            exit_price=Decimal("82000"),
            pnl_usd=Decimal("100"),
            pnl_pct=Decimal("2.0"),
            exit_reason="TP1",
            holding_time_min=15,
        ),
    )
    out_csv = tmp_path / "trades.csv"
    rc = run(db, out_csv)
    assert rc == 0
    out_msg = capsys.readouterr().out
    assert "1 строк" in out_msg
    assert out_csv.exists()
