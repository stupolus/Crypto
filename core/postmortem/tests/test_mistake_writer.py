"""Unit-тесты ``build_mistake_markdown`` / ``write_mistake_document``."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from core.postmortem.mistake_writer import (
    MistakeClassification,
    build_mistake_markdown,
    mistake_filename,
    write_mistake_document,
)
from core.postmortem.models import TradeOutcome


def _make_loss(trade_id: str = "abc12345def") -> TradeOutcome:
    return TradeOutcome(
        trade_id=trade_id,
        symbol="BTC-USDT",
        side="BUY",
        entry_time_ms=1_700_000_000_000,
        entry_price=Decimal("80500"),
        size=Decimal("0.1"),
        exit_time_ms=1_700_000_900_000,  # +15 минут
        exit_price=Decimal("79800"),
        pnl_usd=Decimal("-70"),
        pnl_pct=Decimal("-0.87"),
        exit_reason="SL",
        holding_time_min=15,
        signal_candidate_json='{"action": "BUY", "strategy": "btc_breakout"}',
        market_analyst_json='{"state": "BREAKOUT_PENDING"}',
        sentiment_analyst_json='{"sentiment_score": 0.3}',
        risk_overseer_json='{"approved": true}',
        macro_analyst_json='{"regime": "RISK_ON"}',
        coordinator_json='{"action": "BUY", "composite_confidence": 0.65}',
    )


def _make_classification(
    primary: str = "market_regime_changed",
    secondary: tuple[str, ...] = ("risk_overlooked",),
) -> MistakeClassification:
    return MistakeClassification(
        primary_category=primary,
        secondary_categories=secondary,
        what_went_wrong="Breakout failed — цена быстро вернулась под уровень",
        what_we_should_have_seen="VIX вырос на 12% за час до входа — risk-off",
        confidence_in_diagnosis=0.72,
    )


def test_classification_from_payload() -> None:
    cls = MistakeClassification.from_payload(
        {
            "primary_category": "signal_wrong",
            "secondary_categories": ["sentiment_wrong"],
            "what_went_wrong": "x",
            "what_we_should_have_seen": "y",
            "confidence_in_diagnosis": 0.5,
        }
    )
    assert cls.primary_category == "signal_wrong"
    assert cls.secondary_categories == ("sentiment_wrong",)
    assert cls.confidence_in_diagnosis == 0.5


def test_classification_no_secondary() -> None:
    cls = MistakeClassification.from_payload(
        {
            "primary_category": "signal_wrong",
            "secondary_categories": [],
            "what_went_wrong": "x",
            "what_we_should_have_seen": "y",
            "confidence_in_diagnosis": 0.5,
        }
    )
    assert cls.secondary_categories == ()


def test_markdown_contains_trade_data() -> None:
    md = build_mistake_markdown(_make_loss(), _make_classification())
    assert "BTC-USDT" in md
    assert "abc12345def" in md
    assert "80500" in md
    assert "79800" in md
    assert "-0.87" in md
    assert "SL" in md
    assert "market_regime_changed" in md
    assert "risk_overlooked" in md


def test_markdown_contains_diagnosis() -> None:
    md = build_mistake_markdown(_make_loss(), _make_classification())
    assert "Breakout failed" in md
    assert "VIX вырос" in md
    assert "0.72" in md


def test_markdown_contains_llm_payloads() -> None:
    md = build_mistake_markdown(_make_loss(), _make_classification())
    assert '"action": "BUY"' in md
    assert '"state": "BREAKOUT_PENDING"' in md
    assert '"composite_confidence": 0.65' in md


def test_markdown_rejects_open_trade() -> None:
    outcome = TradeOutcome(
        trade_id="open",
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
    with pytest.raises(ValueError, match="ещё открыт"):
        build_mistake_markdown(outcome, _make_classification())


def test_filename_format() -> None:
    name = mistake_filename(_make_loss(), _make_classification())
    # date: 2023-11-14 (1_700_000_900_000 / 1000 = 2023-11-14 22:28 UTC)
    assert name.startswith("2023-11-14-market_regime_changed-")
    assert name.endswith(".md")
    # short_id = first 8 chars of trade_id "abc12345def"
    assert "abc12345" in name


def test_filename_no_secondary() -> None:
    name = mistake_filename(_make_loss(), _make_classification(secondary=()))
    assert "market_regime_changed" in name


def test_write_creates_file(tmp_path: Path) -> None:
    target = write_mistake_document(_make_loss(), _make_classification(), tmp_path)
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "BTC-USDT" in content
    assert "market_regime_changed" in content


def test_write_creates_parent_dir(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested" / "mistakes"
    target = write_mistake_document(_make_loss(), _make_classification(), nested)
    assert target.exists()
    assert target.parent == nested


def test_write_overwrites_existing(tmp_path: Path) -> None:
    """Atomic rename → второй вызов с тем же trade_id перезаписывает."""
    p1 = write_mistake_document(_make_loss(), _make_classification(), tmp_path)
    p2 = write_mistake_document(
        _make_loss(),
        _make_classification(primary="signal_wrong", secondary=()),
        tmp_path,
    )
    # Разные filenames т.к. category отличается
    assert p1 != p2
    assert p1.exists()
    assert p2.exists()


def test_write_atomic_no_tmp_remains(tmp_path: Path) -> None:
    """После успешной записи не должно остаться .tmp_* файлов."""
    write_mistake_document(_make_loss(), _make_classification(), tmp_path)
    tmp_files = list(tmp_path.glob(".tmp_mistake_*"))
    assert tmp_files == []
