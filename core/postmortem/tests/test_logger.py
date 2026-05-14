"""Unit-тесты ``TradeOutcomeLogger`` — на ephemeral SQLite (tmp_path)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import DecisionContext, ExitData


def _make_ctx(trade_id: str = "t1", side: str = "BUY") -> DecisionContext:
    return DecisionContext(
        trade_id=trade_id,
        symbol="BTC-USDT",
        side=side,
        entry_time_ms=1_700_000_000_000,
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        signal_candidate={"action": side, "strategy": "btc_breakout"},
        market_analyst={"state": "TRENDING_UP"},
        sentiment_analyst={"sentiment_score": 0.4},
        risk_overseer={"approved": True, "max_risk_pct": 1.0},
        macro_analyst={"regime": "RISK_ON"},
        coordinator={"action": side, "composite_confidence": 0.75},
        latency_decision_ms=350,
    )


def _make_exit(reason: str = "TP1", pnl_pct: str = "1.86") -> ExitData:
    return ExitData(
        exit_time_ms=1_700_000_900_000,
        exit_price=Decimal("82000"),
        pnl_usd=Decimal("150"),
        pnl_pct=Decimal(pnl_pct),
        exit_reason=reason,
        holding_time_min=15,
        slippage_bps=Decimal("2.5"),
    )


def test_record_entry_creates_row(tmp_path: Path) -> None:
    db = TradeOutcomeLogger(tmp_path / "test.sqlite")
    db.record_entry(_make_ctx())
    outcome = db.get_by_id("t1")
    assert outcome is not None
    assert outcome.symbol == "BTC-USDT"
    assert outcome.is_closed is False  # exit ещё не записан


def test_record_exit_completes_row(tmp_path: Path) -> None:
    db = TradeOutcomeLogger(tmp_path / "test.sqlite")
    db.record_entry(_make_ctx())
    db.record_exit("t1", _make_exit("TP1"))
    outcome = db.get_by_id("t1")
    assert outcome is not None
    assert outcome.is_closed is True
    assert outcome.is_win is True
    assert outcome.exit_reason == "TP1"
    assert outcome.slippage_bps == Decimal("2.5")


def test_record_exit_without_entry_raises(tmp_path: Path) -> None:
    db = TradeOutcomeLogger(tmp_path / "test.sqlite")
    with pytest.raises(KeyError, match="not_a_trade"):
        db.record_exit("not_a_trade", _make_exit())


def test_get_by_id_missing_returns_none(tmp_path: Path) -> None:
    db = TradeOutcomeLogger(tmp_path / "test.sqlite")
    assert db.get_by_id("missing") is None


def test_record_entry_is_idempotent(tmp_path: Path) -> None:
    """Повторный record_entry с тем же trade_id перезаписывает (для recovery)."""
    db = TradeOutcomeLogger(tmp_path / "test.sqlite")
    db.record_entry(_make_ctx())
    # Меняем что-нибудь и пишем снова
    ctx2 = _make_ctx()
    db.record_entry(ctx2)
    outcome = db.get_by_id("t1")
    assert outcome is not None
    assert outcome.entry_price == Decimal("80500")


def test_recent_losses_filters_and_orders(tmp_path: Path) -> None:
    db = TradeOutcomeLogger(tmp_path / "test.sqlite")
    # Открываем 3 сделки — 2 убыточные, 1 в плюс
    db.record_entry(_make_ctx("loss_old"))
    db.record_entry(_make_ctx("win"))
    db.record_entry(_make_ctx("loss_new"))

    db.record_exit("loss_old", _make_exit("SL", "-0.62"))
    # win — позже по времени
    db.record_exit(
        "win",
        ExitData(
            exit_time_ms=1_700_000_900_000 + 1000,
            exit_price=Decimal("82000"),
            pnl_usd=Decimal("150"),
            pnl_pct=Decimal("1.86"),
            exit_reason="TP1",
            holding_time_min=15,
        ),
    )
    db.record_exit(
        "loss_new",
        ExitData(
            exit_time_ms=1_700_000_900_000 + 2000,
            exit_price=Decimal("80000"),
            pnl_usd=Decimal("-50"),
            pnl_pct=Decimal("-0.5"),
            exit_reason="SL",
            holding_time_min=10,
        ),
    )

    losses = db.recent_losses(limit=10)
    assert len(losses) == 2
    # Должны быть DESC по exit_time_ms → loss_new первый
    assert losses[0].trade_id == "loss_new"
    assert losses[1].trade_id == "loss_old"


def test_recent_losses_respects_limit(tmp_path: Path) -> None:
    db = TradeOutcomeLogger(tmp_path / "test.sqlite")
    for i in range(5):
        db.record_entry(_make_ctx(f"loss_{i}"))
        db.record_exit(
            f"loss_{i}",
            ExitData(
                exit_time_ms=1_700_000_900_000 + i,
                exit_price=Decimal("80000"),
                pnl_usd=Decimal("-10"),
                pnl_pct=Decimal("-0.1"),
                exit_reason="SL",
                holding_time_min=5,
            ),
        )
    losses = db.recent_losses(limit=3)
    assert len(losses) == 3


def test_iter_all_returns_all(tmp_path: Path) -> None:
    db = TradeOutcomeLogger(tmp_path / "test.sqlite")
    db.record_entry(_make_ctx("a"))
    db.record_entry(_make_ctx("b"))
    db.record_entry(_make_ctx("c"))
    all_outcomes = list(db.iter_all())
    assert len(all_outcomes) == 3
    assert {o.trade_id for o in all_outcomes} == {"a", "b", "c"}


def test_llm_payloads_roundtrip(tmp_path: Path) -> None:
    """Проверяем что JSON dict-ы корректно serialize/deserialize."""
    db = TradeOutcomeLogger(tmp_path / "test.sqlite")
    ctx = _make_ctx()
    db.record_entry(ctx)
    outcome = db.get_by_id("t1")
    assert outcome is not None
    assert json.loads(outcome.signal_candidate_json) == ctx.signal_candidate
    assert json.loads(outcome.coordinator_json) == ctx.coordinator
    assert json.loads(outcome.risk_overseer_json) == ctx.risk_overseer


def test_db_path_parent_created(tmp_path: Path) -> None:
    """Logger создаёт parent directory если её нет."""
    nested = tmp_path / "deep" / "nested" / "test.sqlite"
    db = TradeOutcomeLogger(nested)
    db.record_entry(_make_ctx())
    assert nested.exists()
