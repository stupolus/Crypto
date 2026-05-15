"""Unit-тесты ``AssetRegistry`` + session windows."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pytest

from core.assets.registry import (
    DEFAULT_REGISTRY,
    AssetClass,
    AssetRegistry,
    SessionWindow,
    UnknownAssetError,
    is_session_open,
)


def test_default_registry_includes_btc() -> None:
    cfg = DEFAULT_REGISTRY.get("BTC-USDT")
    assert cfg.asset_class == AssetClass.CRYPTO
    assert cfg.max_leverage == 5


def test_default_registry_includes_gold() -> None:
    cfg = DEFAULT_REGISTRY.get("XAU-USDT")
    assert cfg.asset_class == AssetClass.COMMODITY
    assert cfg.max_leverage == 3
    assert cfg.volatility_profile == "normal"


def test_default_registry_includes_oil() -> None:
    cfg = DEFAULT_REGISTRY.get("CL-USDT")
    assert cfg.asset_class == AssetClass.ENERGY
    assert cfg.volatility_profile == "high"


def test_default_registry_includes_tesla() -> None:
    cfg = DEFAULT_REGISTRY.get("TSLA-USDT")
    assert cfg.asset_class == AssetClass.STOCK_PERP
    assert cfg.max_leverage == 3


def test_default_registry_includes_bingx_vst_symbols() -> None:
    """BingX VST реальные имена должны резолвиться через DEFAULT_REGISTRY.

    После 2026-05-15 обнаружили что XAU/CL/TSLA-USDT не существуют на VST,
    реальные имена — XAUT-USDT / NCCO1OILWTI2USD-USDT / NCSKTSLA2USD-USDT.
    """
    assert DEFAULT_REGISTRY.get("XAUT-USDT").asset_class == AssetClass.COMMODITY
    assert DEFAULT_REGISTRY.get("NCCO1OILWTI2USD-USDT").asset_class == AssetClass.ENERGY
    assert DEFAULT_REGISTRY.get("NCSKTSLA2USD-USDT").asset_class == AssetClass.STOCK_PERP
    assert DEFAULT_REGISTRY.get("NCSKNVDA2USD-USDT").asset_class == AssetClass.STOCK_PERP


def test_unknown_symbol_raises() -> None:
    with pytest.raises(UnknownAssetError, match="Unknown symbol"):
        DEFAULT_REGISTRY.get("ZZZ-USDT")


def test_all_symbols_listed() -> None:
    syms = DEFAULT_REGISTRY.all_symbols()
    # Spot-check ключевые
    assert "BTC-USDT" in syms
    assert "XAU-USDT" in syms
    assert "CL-USDT" in syms
    assert "NG-USDT" in syms
    assert "TSLA-USDT" in syms


# ── Session windows ──────────────────────────────────────────────────────────


def test_always_open_session() -> None:
    s = SessionWindow.always_open()
    assert s.is_open(datetime(2026, 5, 14, 3, 0, tzinfo=UTC))  # Thu 03:00
    assert s.is_open(datetime(2026, 5, 17, 23, 30, tzinfo=UTC))  # Sun 23:30


def test_us_market_hours_session() -> None:
    s = SessionWindow.us_market_hours()
    # 14:00 UTC Thu (9:00 AM EST market open period)
    assert s.is_open(datetime(2026, 5, 14, 14, 0, tzinfo=UTC))
    # 13:00 UTC Thu — за 30 мин до открытия
    assert not s.is_open(datetime(2026, 5, 14, 13, 0, tzinfo=UTC))
    # 20:01 UTC Thu — closed
    assert not s.is_open(datetime(2026, 5, 14, 20, 1, tzinfo=UTC))
    # Saturday — closed
    assert not s.is_open(datetime(2026, 5, 16, 14, 0, tzinfo=UTC))


def test_commodity_session() -> None:
    s = SessionWindow.commodity_extended()
    # Thursday — open
    assert s.is_open(datetime(2026, 5, 14, 10, 0, tzinfo=UTC))
    # Saturday — closed
    assert not s.is_open(datetime(2026, 5, 16, 10, 0, tzinfo=UTC))


def test_is_session_open_convenience() -> None:
    """is_session_open(symbol) использует DEFAULT_REGISTRY."""
    thu_morning = datetime(2026, 5, 14, 14, 0, tzinfo=UTC)
    sat_morning = datetime(2026, 5, 16, 14, 0, tzinfo=UTC)

    # BTC всегда открыт
    assert is_session_open("BTC-USDT", thu_morning)
    assert is_session_open("BTC-USDT", sat_morning)

    # TSLA закрыт в субботу
    assert is_session_open("TSLA-USDT", thu_morning)
    assert not is_session_open("TSLA-USDT", sat_morning)


def test_session_window_overnight_wrap() -> None:
    """Если end < start — обработка перехода через полночь."""
    # 22:00 → 06:00 UTC (типа Asian session)
    s = SessionWindow(
        weekdays=frozenset(range(7)),
        start=time(22, 0),
        end=time(6, 0),
    )
    # 23:00 — open (после start)
    assert s.is_open(datetime(2026, 5, 14, 23, 0, tzinfo=UTC))
    # 03:00 — open (до end)
    assert s.is_open(datetime(2026, 5, 14, 3, 0, tzinfo=UTC))
    # 15:00 — closed (в gap'е)
    assert not s.is_open(datetime(2026, 5, 14, 15, 0, tzinfo=UTC))


def test_custom_registry() -> None:
    """Можно построить свой registry для тестов."""
    from decimal import Decimal

    from core.assets.registry import AssetConfig

    reg = AssetRegistry(
        {
            "test_class": AssetConfig(
                asset_class=AssetClass.CRYPTO,
                session=SessionWindow.always_open(),
                max_leverage=10,
                volatility_profile="high",
                min_notional_usdt=Decimal("1"),
                base_symbols=("TEST",),
            )
        }
    )
    assert reg.get("TEST-USDT").max_leverage == 10
    with pytest.raises(UnknownAssetError):
        reg.get("BTC-USDT")
