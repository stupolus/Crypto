"""Unit-тесты ``scripts.process_mistakes``."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.agents.base import AgentResponse
from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.mistake_classifier import MistakeClassifierAgent
from core.postmortem.models import DecisionContext, ExitData
from scripts.process_mistakes import process_one, run


def _record_loss(
    log: TradeOutcomeLogger,
    *,
    trade_id: str = "lossA",
    pnl_pct: str = "-1.5",
) -> None:
    ctx = DecisionContext(
        trade_id=trade_id,
        symbol="BTC-USDT",
        side="BUY",
        entry_time_ms=1_700_000_000_000,
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        signal_candidate={"action": "BUY"},
        market_analyst={"state": "BREAKOUT_PENDING"},
        sentiment_analyst={"sentiment_score": 0.3},
        risk_overseer={"approved": True},
        macro_analyst={"regime": "RISK_ON"},
        coordinator={"action": "BUY", "composite_confidence": 0.65},
    )
    log.record_entry(ctx)
    log.record_exit(
        trade_id,
        ExitData(
            exit_time_ms=1_700_000_900_000,
            exit_price=Decimal("79800"),
            pnl_usd=Decimal("-70"),
            pnl_pct=Decimal(pnl_pct),
            exit_reason="SL",
            holding_time_min=15,
        ),
    )


def _record_win(log: TradeOutcomeLogger, *, trade_id: str = "winA") -> None:
    ctx = DecisionContext(
        trade_id=trade_id,
        symbol="BTC-USDT",
        side="BUY",
        entry_time_ms=1_700_000_000_000,
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        signal_candidate={"action": "BUY"},
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
            exit_time_ms=1_700_000_900_000,
            exit_price=Decimal("82000"),
            pnl_usd=Decimal("150"),
            pnl_pct=Decimal("2.0"),
            exit_reason="TP1",
            holding_time_min=15,
        ),
    )


def _make_classifier_mock(
    payload: dict[str, Any] | None = None,
    raises: Exception | None = None,
) -> MistakeClassifierAgent:
    """Подделанный MistakeClassifierAgent с заданным response."""
    mock = MagicMock(spec=MistakeClassifierAgent)
    if raises is not None:
        mock.run = AsyncMock(side_effect=raises)
    else:
        default_payload: dict[str, Any] = {
            "primary_category": "market_regime_changed",
            "secondary_categories": [],
            "what_went_wrong": "test",
            "what_we_should_have_seen": "test",
            "confidence_in_diagnosis": 0.7,
        }
        used = payload if payload is not None else default_payload
        mock.run = AsyncMock(
            return_value=AgentResponse(
                payload=used,
                raw_text="",
                tokens_in=0,
                tokens_out=0,
                model="claude-sonnet-4-6",
            )
        )
    return mock


def _get_loss_outcome(log: TradeOutcomeLogger, trade_id: str) -> Any:
    out = log.get_by_id(trade_id)
    assert out is not None
    return out


@pytest.mark.asyncio
async def test_process_one_writes_new_markdown(tmp_path: Path) -> None:
    db = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _record_loss(db, trade_id="lossA")
    outcome = _get_loss_outcome(db, "lossA")
    out_dir = tmp_path / "mistakes"
    out_dir.mkdir()
    classifier = _make_classifier_mock()

    result = await process_one(outcome, classifier, out_dir)
    assert result.status == "written"
    files = list(out_dir.glob("*.md"))
    assert len(files) == 1
    assert "lossA" in files[0].name or "lossA"[:8] in files[0].name


@pytest.mark.asyncio
async def test_process_one_skip_existing(tmp_path: Path) -> None:
    db = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _record_loss(db, trade_id="lossB")
    outcome = _get_loss_outcome(db, "lossB")
    out_dir = tmp_path / "mistakes"
    out_dir.mkdir()
    classifier = _make_classifier_mock()

    # Первый раз — written
    await process_one(outcome, classifier, out_dir)
    # Второй раз — skip
    result = await process_one(outcome, classifier, out_dir)
    assert result.status == "skipped"


@pytest.mark.asyncio
async def test_process_one_overwrite_runs_again(tmp_path: Path) -> None:
    db = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _record_loss(db, trade_id="lossC")
    outcome = _get_loss_outcome(db, "lossC")
    out_dir = tmp_path / "mistakes"
    out_dir.mkdir()
    classifier = _make_classifier_mock()

    await process_one(outcome, classifier, out_dir)
    result = await process_one(outcome, classifier, out_dir, overwrite=True)
    assert result.status == "written"


@pytest.mark.asyncio
async def test_process_one_classifier_failure_returns_failed(tmp_path: Path) -> None:
    db = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _record_loss(db, trade_id="lossD")
    outcome = _get_loss_outcome(db, "lossD")
    out_dir = tmp_path / "mistakes"
    out_dir.mkdir()
    classifier = _make_classifier_mock(raises=RuntimeError("rate limit"))

    result = await process_one(outcome, classifier, out_dir)
    assert result.status == "failed"
    assert list(out_dir.glob("*.md")) == []


@pytest.mark.asyncio
async def test_process_one_invalid_payload_returns_failed(tmp_path: Path) -> None:
    db = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _record_loss(db, trade_id="lossE")
    outcome = _get_loss_outcome(db, "lossE")
    out_dir = tmp_path / "mistakes"
    out_dir.mkdir()
    # Invalid payload — нет required field 'what_went_wrong'
    classifier = _make_classifier_mock(payload={"primary_category": "signal_wrong"})

    result = await process_one(outcome, classifier, out_dir)
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_run_missing_db(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = await run(tmp_path / "nope.sqlite", tmp_path / "out", limit=10)
    assert rc == 1
    err = capsys.readouterr().err
    assert "DB не существует" in err


@pytest.mark.asyncio
async def test_run_no_anthropic_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Без ANTHROPIC_API_KEY скрипт должен честно отказаться."""
    db = TradeOutcomeLogger(tmp_path / "db.sqlite")
    _record_loss(db)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # ВАЖНО: pydantic_settings подхватывает .env из репо. Если ключ там
    # есть — этот тест ложно проходит. В CI .env отсутствует, но локально
    # пропускаем.
    from core.agents.settings import AnthropicSettings

    if AnthropicSettings().configured:
        pytest.skip("ANTHROPIC_API_KEY присутствует в .env — пропускаем negative test")
    rc = await run(tmp_path / "db.sqlite", tmp_path / "out", limit=10)
    assert rc == 1
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY" in err


@pytest.mark.asyncio
async def test_run_empty_db_returns_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-for-init")
    db = TradeOutcomeLogger(tmp_path / "db.sqlite")
    rc = await run(tmp_path / "db.sqlite", tmp_path / "out", limit=10)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Нет убыточных" in out
    _ = db
