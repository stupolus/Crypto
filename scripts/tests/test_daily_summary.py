"""Unit-тесты ``scripts.daily_summary``."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import DecisionContext, ExitData
from scripts.daily_summary import (
    _format_header,
    _format_period_section,
    _format_quick_stats,
    run,
)

_NOW_MS = 1_700_000_000_000


def _add(
    log: TradeOutcomeLogger,
    *,
    trade_id: str,
    entry_offset_days: int = 1,
    is_loss: bool = False,
) -> None:
    entry_ms = _NOW_MS - entry_offset_days * 86_400_000
    ctx = DecisionContext(
        trade_id=trade_id,
        symbol="BTC-USDT",
        side="BUY",
        entry_time_ms=entry_ms,
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
        trade_id,
        ExitData(
            exit_time_ms=entry_ms + 900_000,
            exit_price=Decimal("79000") if is_loss else Decimal("82000"),
            pnl_usd=Decimal("-50") if is_loss else Decimal("100"),
            pnl_pct=Decimal("-1.5") if is_loss else Decimal("2.0"),
            exit_reason="SL" if is_loss else "TP1",
            holding_time_min=15,
        ),
    )


def test_format_header_includes_timestamp() -> None:
    text = _format_header()
    assert "# Daily Summary" in text
    assert "UTC" in text


def test_format_quick_stats_missing_db(tmp_path: Path) -> None:
    text = _format_quick_stats(tmp_path / "no.sqlite")
    assert "Quick Stats" in text
    assert "ещё не создана" in text


def test_format_quick_stats_with_data(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    log = TradeOutcomeLogger(db)
    _add(log, trade_id="w1")
    _add(log, trade_id="l1", is_loss=True)
    text = _format_quick_stats(db)
    assert "Total trades:" in text
    assert "Win rate:" in text


def test_format_period_section_uses_weekly_review(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    log = TradeOutcomeLogger(db)
    _add(log, trade_id="recent", entry_offset_days=2)
    text = _format_period_section(db, days=7, now_ms=_NOW_MS)
    assert "Weekly Review" in text


def test_format_period_section_missing_db_empty(tmp_path: Path) -> None:
    text = _format_period_section(tmp_path / "no.sqlite", days=7, now_ms=_NOW_MS)
    assert text == ""


def test_run_combines_sections(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    log = TradeOutcomeLogger(db)
    _add(log, trade_id="w1", entry_offset_days=1)
    text = run(db, days=7, now_ms=_NOW_MS)
    assert "# Daily Summary" in text
    assert "Quick Stats" in text
    assert "Weekly Review" in text


def test_run_handles_empty_db(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    TradeOutcomeLogger(db)
    text = run(db, days=7, now_ms=_NOW_MS)
    assert "# Daily Summary" in text
    assert "Total trades:    0" in text
