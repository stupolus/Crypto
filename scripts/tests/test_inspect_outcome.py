"""Unit-тесты ``scripts.inspect_outcome``."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import DecisionContext, ExitData
from scripts.inspect_outcome import _format_outcome, _pretty_json, find_outcome, run


def _seed(log: TradeOutcomeLogger, trade_id: str = "abc12345xyz") -> None:
    ctx = DecisionContext(
        trade_id=trade_id,
        symbol="BTC-USDT",
        side="BUY",
        entry_time_ms=1_700_000_000_000,
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        signal_candidate={"action": "BUY", "score": 0.7},
        market_analyst={"state": "TRENDING_UP"},
        sentiment_analyst={"sentiment_score": 0.5},
        risk_overseer={"approved": True, "max_risk_pct": 1.0},
        macro_analyst={"regime": "RISK_ON"},
        coordinator={"action": "BUY", "composite_confidence": 0.75},
        latency_decision_ms=420,
    )
    log.record_entry(ctx)


def test_pretty_json_valid() -> None:
    text = _pretty_json('{"action": "BUY", "score": 0.7}')
    assert '"action": "BUY"' in text
    assert "\n" in text  # multi-line indented


def test_pretty_json_invalid_returns_as_is() -> None:
    raw = "not valid json {"
    assert _pretty_json(raw) == raw


def test_format_outcome_open(tmp_path: Path) -> None:
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _seed(log, "open1")
    outcome = log.get_by_id("open1")
    assert outcome is not None
    text = _format_outcome(outcome)
    assert "# Trade open1" in text
    assert "**Status:** OPEN" in text
    assert "TRENDING_UP" in text
    assert "Decision latency:** 420 ms" in text


def test_format_outcome_closed(tmp_path: Path) -> None:
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _seed(log, "closed1")
    log.record_exit(
        "closed1",
        ExitData(
            exit_time_ms=1_700_000_900_000,
            exit_price=Decimal("82000"),
            pnl_usd=Decimal("150"),
            pnl_pct=Decimal("1.86"),
            exit_reason="TP1",
            holding_time_min=15,
        ),
    )
    outcome = log.get_by_id("closed1")
    assert outcome is not None
    text = _format_outcome(outcome)
    assert "**Exit reason:** TP1" in text
    assert "1.86%" in text
    assert "**Holding:** 15 min" in text


def test_find_outcome_exact_match(tmp_path: Path) -> None:
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _seed(log, "abc12345")
    result = find_outcome(log, "abc12345")
    assert result is not None
    assert result.trade_id == "abc12345"


def test_find_outcome_prefix_match(tmp_path: Path) -> None:
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _seed(log, "abc12345xyz")
    result = find_outcome(log, "abc123")
    assert result is not None
    assert result.trade_id == "abc12345xyz"


def test_find_outcome_no_match(tmp_path: Path) -> None:
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _seed(log, "abc12345")
    assert find_outcome(log, "xyz") is None


def test_find_outcome_prefix_returns_most_recent(tmp_path: Path) -> None:
    """При нескольких prefix match'ах возвращаем самый recent."""
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    # Same prefix, разные entry_time_ms
    log.record_entry(
        DecisionContext(
            trade_id="abc_old",
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
    )
    log.record_entry(
        DecisionContext(
            trade_id="abc_new",
            symbol="BTC-USDT",
            side="BUY",
            entry_time_ms=1_700_000_500_000,  # newer
            entry_price=Decimal("80500"),
            size=Decimal("0.1"),
            signal_candidate={},
            market_analyst={},
            sentiment_analyst={},
            risk_overseer={},
            macro_analyst={},
            coordinator={},
        )
    )
    result = find_outcome(log, "abc")
    assert result is not None
    assert result.trade_id == "abc_new"


def test_run_missing_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = run(tmp_path / "no.sqlite", "anything")
    assert rc == 1
    assert "не существует" in capsys.readouterr().err


def test_run_no_match(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _seed(log)
    rc = run(tmp_path / "db.sqlite", "no_such_trade")
    assert rc == 2
    assert "не найден" in capsys.readouterr().err


def test_run_happy_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _seed(log, "t1")
    rc = run(tmp_path / "db.sqlite", "t1")
    assert rc == 0
    out = capsys.readouterr().out
    assert "# Trade t1" in out
    assert "Market Analyst" in out
    assert "TRENDING_UP" in out
