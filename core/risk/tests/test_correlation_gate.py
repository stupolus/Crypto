"""Тесты correlation gate — max 1 позиция на asset class."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.risk import check_correlation


@dataclass(frozen=True)
class _Pos:
    symbol: str
    position_amount: Decimal


def test_no_open_positions_allows() -> None:
    d = check_correlation("BTC-USDT", [])
    assert d.allowed is True
    assert d.reason == "ok"


def test_same_symbol_does_not_block() -> None:
    """Открытая позиция по тому же symbol — не correlation, это 'уже в рынке'."""
    positions = [_Pos("BTC-USDT", Decimal("0.5"))]
    d = check_correlation("BTC-USDT", positions)
    assert d.allowed is True


def test_different_asset_class_allowed() -> None:
    """BTC (crypto) открыт → XAUT (commodity) можно открыть."""
    positions = [_Pos("BTC-USDT", Decimal("0.5"))]
    d = check_correlation("XAUT-USDT", positions)
    assert d.allowed is True


def test_same_asset_class_blocks() -> None:
    """TSLA (stock_perp) открыт → NVDA (stock_perp) блокируется."""
    positions = [_Pos("NCSKTSLA2USD-USDT", Decimal("3"))]
    d = check_correlation("NCSKNVDA2USD-USDT", positions)
    assert d.allowed is False
    assert "correlation_block" in d.reason
    assert "stock_perp" in d.reason


def test_zero_amount_position_ignored() -> None:
    """BingX отдаёт 'слоты' с position_amount=0 — не считаем за открытую."""
    positions = [_Pos("NCSKTSLA2USD-USDT", Decimal("0"))]
    d = check_correlation("NCSKNVDA2USD-USDT", positions)
    assert d.allowed is True


def test_unknown_asset_class_skips_gracefully() -> None:
    """Неизвестный symbol → пропускаем (RiskEngine всё равно проверит)."""
    d = check_correlation("ZZZ-UNKNOWN", [_Pos("BTC-USDT", Decimal("1"))])
    assert d.allowed is True
    assert d.reason == "unknown_asset_class_skip"


def test_commodity_pair_blocks_within_class() -> None:
    """XAUT (commodity) открыт → XAG (commodity, silver) блокируется."""
    positions = [_Pos("XAUT-USDT", Decimal("1"))]
    d = check_correlation("XAG-USDT", positions)
    assert d.allowed is False
    assert "commodity" in d.reason


def test_legacy_alias_symbols_resolve() -> None:
    """Старые имена (XAU-USDT) тоже резолвятся в commodity через registry."""
    positions = [_Pos("XAU-USDT", Decimal("1"))]
    d = check_correlation("XAUT-USDT", positions)
    assert d.allowed is False  # оба commodity
