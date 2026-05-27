"""Тесты cross-venue: маппинг + ratio-перенос."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.data.cross_venue import (
    CROSS_VENUE_PAIRS,
    bingx_to_bybit,
    bybit_to_bingx,
    cross_venue_price_ratio,
    transfer_price_level,
    validate_side,
)

# ── Symbol mapping ───────────────────────────────────────────────────────────


def test_bingx_to_bybit_known_majors() -> None:
    assert bingx_to_bybit("BTC-USDT") == "BTC-USDT"
    assert bingx_to_bybit("ETH-USDT") == "ETH-USDT"
    assert bingx_to_bybit("SOL-USDT") == "SOL-USDT"


def test_bingx_to_bybit_rwa_proxy_gold() -> None:
    """BingX-GOLD-перп → Bybit XAUT (tokenized gold proxy)."""
    assert bingx_to_bybit("NCCOGOLD2USD-USDT") == "XAUT-USDT"


def test_bingx_to_bybit_unknown_returns_none() -> None:
    """Прокси для случайных стоков нет — None."""
    assert bingx_to_bybit("NCSKTSLA2USD-USDT") is None
    assert bingx_to_bybit("UNKNOWN-USDT") is None


def test_bybit_to_bingx_reverse() -> None:
    assert bybit_to_bingx("BTC-USDT") == "BTC-USDT"
    assert bybit_to_bingx("XAUT-USDT") == "NCCOGOLD2USD-USDT"


def test_bybit_to_bingx_accepts_no_hyphen() -> None:
    """Bybit-формат без дефиса (BTCUSDT) тоже принимается."""
    assert bybit_to_bingx("BTCUSDT") == "BTC-USDT"
    assert bybit_to_bingx("ETHUSDT") == "ETH-USDT"
    assert bybit_to_bingx("XAUTUSDT") == "NCCOGOLD2USD-USDT"


def test_bybit_to_bingx_unknown_returns_none() -> None:
    assert bybit_to_bingx("FAKEUSDT") is None


def test_registry_no_duplicate_bingx_symbols() -> None:
    """Реестр без дублей на BingX-стороне (иначе bingx_to_bybit неоднозначен)."""
    bingx = [p.bingx for p in CROSS_VENUE_PAIRS]
    assert len(bingx) == len(set(bingx))


def test_registry_no_duplicate_bybit_symbols() -> None:
    """Реестр без дублей на Bybit-стороне (иначе bybit_to_bingx неоднозначен)."""
    bybit = [p.bybit for p in CROSS_VENUE_PAIRS]
    assert len(bybit) == len(set(bybit))


# ── Ratio ────────────────────────────────────────────────────────────────────


def test_cross_venue_ratio_simple() -> None:
    """ratio = bingx/bybit."""
    r = cross_venue_price_ratio(Decimal("35100"), Decimal("35000"))
    assert r == Decimal("35100") / Decimal("35000")


def test_cross_venue_ratio_zero_or_negative_raises() -> None:
    with pytest.raises(ValueError):
        cross_venue_price_ratio(Decimal("100"), Decimal("0"))
    with pytest.raises(ValueError):
        cross_venue_price_ratio(Decimal("0"), Decimal("100"))
    with pytest.raises(ValueError):
        cross_venue_price_ratio(Decimal("-1"), Decimal("100"))


def test_transfer_price_level_classic_example() -> None:
    """Сигнал на Bybit SMA200=30000, close 35000; BingX close 35100 →
    эквивалентный уровень на BingX ≈ 30085.71."""
    target = transfer_price_level(
        level_on_source=Decimal("30000"),
        source_close=Decimal("35000"),
        target_close=Decimal("35100"),
    )
    expected = Decimal("30000") * Decimal("35100") / Decimal("35000")
    assert target == expected


def test_transfer_price_level_identity_when_closes_match() -> None:
    """Если close-цены совпадают — уровень переносится 1-в-1."""
    target = transfer_price_level(
        level_on_source=Decimal("30000"),
        source_close=Decimal("35000"),
        target_close=Decimal("35000"),
    )
    assert target == Decimal("30000")


def test_transfer_price_level_validates_positives() -> None:
    with pytest.raises(ValueError):
        transfer_price_level(
            level_on_source=Decimal("0"),
            source_close=Decimal("1"),
            target_close=Decimal("1"),
        )
    with pytest.raises(ValueError):
        transfer_price_level(
            level_on_source=Decimal("1"),
            source_close=Decimal("0"),
            target_close=Decimal("1"),
        )
    with pytest.raises(ValueError):
        transfer_price_level(
            level_on_source=Decimal("1"),
            source_close=Decimal("1"),
            target_close=Decimal("0"),
        )


# ── validate_side ────────────────────────────────────────────────────────────


def test_validate_side_accepts_buy_sell() -> None:
    assert validate_side("BUY") == "BUY"
    assert validate_side("SELL") == "SELL"


def test_validate_side_rejects_other() -> None:
    with pytest.raises(ValueError, match="must be"):
        validate_side("HOLD")
    with pytest.raises(ValueError):
        validate_side("buy")  # case-sensitive
