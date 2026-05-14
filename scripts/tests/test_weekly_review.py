"""Unit-тесты ``scripts.weekly_review``."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import DecisionContext, ExitData
from scripts.weekly_review import (
    compute_period_summary,
    format_summary,
    mistake_category_summary,
    run,
)

_DAY_MS = 86_400_000
_NOW_MS = 1_700_000_000_000


def _add(
    log: TradeOutcomeLogger,
    *,
    trade_id: str,
    entry_offset_days: int,
    is_loss: bool = False,
    exit_reason: str = "TP1",
    pnl_pct: str = "1.5",
    holding_min: int = 15,
) -> None:
    entry_ms = _NOW_MS - entry_offset_days * _DAY_MS
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
            exit_time_ms=entry_ms + holding_min * 60_000,
            exit_price=Decimal("79000") if is_loss else Decimal("82000"),
            pnl_usd=Decimal("-50") if is_loss else Decimal("100"),
            pnl_pct=Decimal(pnl_pct) if is_loss is False else Decimal("-" + pnl_pct.lstrip("-")),
            exit_reason=exit_reason,
            holding_time_min=holding_min,
        ),
    )


def test_summary_empty() -> None:
    s = compute_period_summary([], cutoff_ms=0, days=7)
    assert s.total == 0
    assert s.wins == 0
    assert s.losses == 0
    assert s.win_rate_pct == Decimal("0")


def test_summary_only_within_period(tmp_path: Path) -> None:
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _add(log, trade_id="recent", entry_offset_days=2, is_loss=False, pnl_pct="2.0")
    _add(log, trade_id="too_old", entry_offset_days=30, is_loss=True, pnl_pct="-1.0")
    outcomes = list(log.iter_all())
    cutoff_ms = _NOW_MS - 7 * _DAY_MS
    s = compute_period_summary(outcomes, cutoff_ms=cutoff_ms, days=7)
    assert s.total == 1
    assert s.wins == 1
    assert s.losses == 0


def test_summary_win_rate_calculation(tmp_path: Path) -> None:
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _add(log, trade_id="w1", entry_offset_days=1, pnl_pct="2.0")
    _add(log, trade_id="w2", entry_offset_days=2, pnl_pct="1.5")
    _add(log, trade_id="l1", entry_offset_days=3, is_loss=True, exit_reason="SL", pnl_pct="-1.0")
    outcomes = list(log.iter_all())
    cutoff_ms = _NOW_MS - 7 * _DAY_MS
    s = compute_period_summary(outcomes, cutoff_ms=cutoff_ms, days=7)
    assert s.wins == 2
    assert s.losses == 1
    # 2/3 = 66.7%
    assert s.win_rate_pct == Decimal("66.7")
    assert s.avg_win_pct == Decimal("1.75")
    assert s.avg_loss_pct == Decimal("-1.00")


def test_summary_exit_reasons_counted(tmp_path: Path) -> None:
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _add(log, trade_id="a", entry_offset_days=1, exit_reason="TP1")
    _add(log, trade_id="b", entry_offset_days=2, exit_reason="TP1")
    _add(log, trade_id="c", entry_offset_days=3, exit_reason="SL", is_loss=True)
    outcomes = list(log.iter_all())
    cutoff_ms = _NOW_MS - 7 * _DAY_MS
    s = compute_period_summary(outcomes, cutoff_ms=cutoff_ms, days=7)
    assert s.exit_reason_counts["TP1"] == 2
    assert s.exit_reason_counts["SL"] == 1


def test_top_losses_ordered(tmp_path: Path) -> None:
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _add(log, trade_id="small", entry_offset_days=1, is_loss=True, pnl_pct="-0.3", exit_reason="SL")
    _add(log, trade_id="big", entry_offset_days=2, is_loss=True, pnl_pct="-2.5", exit_reason="SL")
    _add(log, trade_id="med", entry_offset_days=3, is_loss=True, pnl_pct="-1.0", exit_reason="SL")
    outcomes = list(log.iter_all())
    s = compute_period_summary(outcomes, cutoff_ms=0, days=7, top_losses_n=2)
    # Самые крупные сначала (наиболее negative)
    assert len(s.top_losses) == 2
    assert s.top_losses[0].trade_id == "big"
    assert s.top_losses[1].trade_id == "med"


def test_format_summary_contains_sections(tmp_path: Path) -> None:
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _add(log, trade_id="w1", entry_offset_days=1, pnl_pct="2.0")
    _add(log, trade_id="l1", entry_offset_days=2, is_loss=True, pnl_pct="-1.0", exit_reason="SL")
    outcomes = list(log.iter_all())
    s = compute_period_summary(outcomes, cutoff_ms=_NOW_MS - 7 * _DAY_MS, days=7)
    text = format_summary(s)
    assert "Weekly Review" in text
    assert "Total trades:" in text
    assert "Win rate:" in text
    assert "Exit reasons" in text
    assert "Top losses" in text
    assert "l1" in text


def test_mistake_category_summary_empty_dir(tmp_path: Path) -> None:
    empty_dir = tmp_path / "mistakes"
    empty_dir.mkdir()
    assert mistake_category_summary(empty_dir) == ""


def test_mistake_category_summary_missing_dir(tmp_path: Path) -> None:
    assert mistake_category_summary(tmp_path / "nonexistent") == ""


def test_mistake_category_summary_parses_files(tmp_path: Path) -> None:
    md_dir = tmp_path / "mistakes"
    md_dir.mkdir()
    (md_dir / "a.md").write_text(
        "# Mistake: market_regime_changed\n\nLorem ipsum",
        encoding="utf-8",
    )
    (md_dir / "b.md").write_text(
        "# Mistake: market_regime_changed\n\nMore text",
        encoding="utf-8",
    )
    (md_dir / "c.md").write_text(
        "# Mistake: signal_wrong\n\nText",
        encoding="utf-8",
    )
    text = mistake_category_summary(md_dir)
    assert "market_regime_changed: 2" in text
    assert "signal_wrong: 1" in text


def test_run_end_to_end(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    log = TradeOutcomeLogger(db)
    _add(log, trade_id="recent_win", entry_offset_days=1, pnl_pct="2.0")
    text = run(db, days=7, mistakes_dir=None, now_ms=_NOW_MS)
    assert "Weekly Review" in text
    assert "recent_win" not in text  # winner не в top losses
    assert "**Win rate:** 100.0%" in text
