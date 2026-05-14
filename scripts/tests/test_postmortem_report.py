"""Unit-тесты ``scripts.postmortem_report``."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import DecisionContext, ExitData, TradeOutcome
from scripts.postmortem_report import (
    Summary,
    compute_summary,
    format_recent_losses,
    format_summary,
    run,
)


def _make_outcome(
    *,
    trade_id: str,
    is_loss: bool = False,
    is_open: bool = False,
) -> TradeOutcome:
    base: dict[str, object] = {
        "trade_id": trade_id,
        "symbol": "BTC-USDT",
        "side": "BUY",
        "entry_time_ms": 1_700_000_000_000,
        "entry_price": Decimal("80500"),
        "size": Decimal("0.1"),
        "signal_candidate_json": "{}",
        "market_analyst_json": "{}",
        "sentiment_analyst_json": "{}",
        "risk_overseer_json": "{}",
        "macro_analyst_json": "{}",
        "coordinator_json": "{}",
    }
    if is_open:
        return TradeOutcome(**base)
    base.update(
        exit_time_ms=1_700_000_900_000,
        exit_price=Decimal("79000") if is_loss else Decimal("82000"),
        pnl_usd=Decimal("-50") if is_loss else Decimal("100"),
        pnl_pct=Decimal("-1.5") if is_loss else Decimal("2.0"),
        exit_reason="SL" if is_loss else "TP1",
        holding_time_min=15,
    )
    return TradeOutcome(**base)


def test_compute_summary_empty() -> None:
    s = compute_summary([])
    assert s.total == 0
    assert s.closed == 0
    assert s.wins == 0
    assert s.losses == 0
    assert s.win_rate_pct == Decimal("0")


def test_compute_summary_only_open() -> None:
    s = compute_summary(
        [_make_outcome(trade_id="t1", is_open=True), _make_outcome(trade_id="t2", is_open=True)]
    )
    assert s.total == 2
    assert s.open_trades == 2
    assert s.closed == 0
    assert s.win_rate_pct == Decimal("0")


def test_compute_summary_mixed() -> None:
    outcomes = [
        _make_outcome(trade_id="w1"),  # win
        _make_outcome(trade_id="w2"),
        _make_outcome(trade_id="l1", is_loss=True),  # loss
        _make_outcome(trade_id="open", is_open=True),
    ]
    s = compute_summary(outcomes)
    assert s.total == 4
    assert s.open_trades == 1
    assert s.closed == 3
    assert s.wins == 2
    assert s.losses == 1
    # 2/3 = 66.7%
    assert s.win_rate_pct == Decimal("66.7")
    assert s.avg_win_pct == Decimal("2.00")
    assert s.avg_loss_pct == Decimal("-1.50")


def test_format_summary_renders_all_fields() -> None:
    s = Summary(
        total=10,
        open_trades=1,
        closed=9,
        wins=6,
        losses=3,
        flat=0,
        win_rate_pct=Decimal("66.7"),
        avg_win_pct=Decimal("2.50"),
        avg_loss_pct=Decimal("-1.20"),
    )
    text = format_summary(s)
    assert "Total trades:    10" in text
    assert "Win rate:        66.7%" in text
    assert "Avg win:         2.50%" in text
    assert "Avg loss:        -1.20%" in text


def test_format_recent_losses_empty() -> None:
    text = format_recent_losses([], limit=5)
    assert "нет убыточных" in text


def test_format_recent_losses_with_data() -> None:
    losses = [
        _make_outcome(trade_id="abc12345", is_loss=True),
        _make_outcome(trade_id="def67890", is_loss=True),
    ]
    text = format_recent_losses(losses, limit=5)
    assert "abc12345" in text
    assert "def67890" in text
    assert "SL" in text
    assert "-1.5" in text


def test_run_missing_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(tmp_path / "missing.sqlite", losses_limit=5)
    assert rc == 1
    err = capsys.readouterr().err
    assert "не существует" in err


def test_run_empty_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "test.sqlite"
    TradeOutcomeLogger(db)  # создаёт пустую БД
    rc = run(db, losses_limit=5)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Total trades:    0" in out


def test_run_populated_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "test.sqlite"
    log = TradeOutcomeLogger(db)
    # одна win + одна loss
    for tid, loss in [("win1", False), ("loss1", True)]:
        ctx = DecisionContext(
            trade_id=tid,
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
            tid,
            ExitData(
                exit_time_ms=1_700_000_900_000,
                exit_price=Decimal("79000") if loss else Decimal("82000"),
                pnl_usd=Decimal("-50") if loss else Decimal("100"),
                pnl_pct=Decimal("-1.5") if loss else Decimal("2.0"),
                exit_reason="SL" if loss else "TP1",
                holding_time_min=15,
            ),
        )
    rc = run(db, losses_limit=10)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Total trades:    2" in out
    assert "loss1" in out
    assert "Win rate:        50.0%" in out
