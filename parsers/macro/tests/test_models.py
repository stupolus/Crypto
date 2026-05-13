"""Unit-тесты ``parsers.macro.models``."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from parsers.macro.models import MacroSnapshot, YfinanceQuote


def test_yfinance_quote_basic() -> None:
    q = YfinanceQuote(
        symbol="DX-Y.NYB",
        timestamp_ms=1_700_000_000_000,
        last=Decimal("104.5"),
        change_pct_24h=Decimal("0.5"),
        volume_24h=Decimal("100000"),
    )
    assert q.symbol == "DX-Y.NYB"
    assert q.last == Decimal("104.5")


def test_yfinance_quote_immutable() -> None:
    q = YfinanceQuote(symbol="X", timestamp_ms=1_700_000_000_000, last=Decimal("1"))
    with pytest.raises(ValidationError):
        q.last = Decimal("2")  # type: ignore[misc]


def test_yfinance_quote_empty_symbol_rejected() -> None:
    with pytest.raises(ValidationError):
        YfinanceQuote(symbol="", timestamp_ms=1_700_000_000_000, last=Decimal("1"))


def test_yfinance_quote_negative_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        YfinanceQuote(symbol="X", timestamp_ms=-1, last=Decimal("1"))


def test_macro_snapshot_all_optional() -> None:
    """Все макро-поля Optional — снапшот валиден даже если источники down."""
    snap = MacroSnapshot(timestamp_ms=1_700_000_000_000)
    assert snap.dxy is None
    assert snap.vix is None
    assert snap.warnings == ()


def test_macro_snapshot_filled() -> None:
    snap = MacroSnapshot(
        timestamp_ms=1_700_000_000_000,
        dxy=Decimal("104.5"),
        vix=Decimal("18.2"),
        spx=Decimal("4500"),
        gold=Decimal("2050"),
        yield_10y=Decimal("4.25"),
        warnings=("yfinance partial — NDX skipped",),
    )
    assert snap.dxy == Decimal("104.5")
    assert len(snap.warnings) == 1


def test_macro_snapshot_ignores_unknown_fields() -> None:
    snap = MacroSnapshot(
        timestamp_ms=1_700_000_000_000,
        dxy=Decimal("104.5"),
        unknown_field="ignored",
    )
    assert snap.dxy == Decimal("104.5")
