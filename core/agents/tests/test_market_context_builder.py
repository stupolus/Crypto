"""Unit-тесты ``MarketContextBuilder``."""

from __future__ import annotations

import json
from decimal import Decimal

from adapters.bingx.models import Kline
from core.agents.evaluate import MarketContextData
from core.agents.market_context_builder import MarketBuilderConfig, MarketContextBuilder


def _make_kline(time_ms: int, close: Decimal, *, high: Decimal | None = None) -> Kline:
    h = high if high is not None else close + Decimal("10")
    return Kline.model_validate(
        {
            "time": time_ms,
            "open": str(close - Decimal("5")),
            "high": str(h),
            "low": str(close - Decimal("15")),
            "close": str(close),
            "volume": "100",
        }
    )


def _make_history(
    n: int, base: Decimal = Decimal("80000"), step: Decimal = Decimal("10")
) -> list[Kline]:
    return [_make_kline(1_700_000_000_000 + i * 900_000, base + step * i) for i in range(n)]


def test_builder_with_full_history_returns_indicators() -> None:
    history = _make_history(60)
    builder = MarketContextBuilder()
    ctx = builder.build(history=history)

    assert isinstance(ctx, MarketContextData)
    # ATR / Donchian / EMA должны быть не "0"
    assert ctx.atr != "0"
    assert ctx.donchian_high != "0"
    assert ctx.donchian_low != "0"
    assert ctx.ema20 != "0"
    assert ctx.ema50 != "0"
    # ohlcv JSON разворачивается в список
    parsed = json.loads(ctx.ohlcv_recent_json)
    assert isinstance(parsed, list)
    assert len(parsed) == MarketBuilderConfig().ohlcv_recent_n
    assert parsed[-1]["close"] == str(history[-1].close)


def test_builder_empty_history_returns_defaults() -> None:
    builder = MarketContextBuilder()
    ctx = builder.build(history=[])
    assert ctx.atr == "0"
    assert ctx.donchian_high == "0"
    assert ctx.donchian_low == "0"
    assert ctx.ema20 == "0"
    assert ctx.ema50 == "0"
    assert ctx.ohlcv_recent_json == "[]"


def test_builder_short_history_partial_indicators() -> None:
    """Если есть 10 свечей — ATR(14) недоступен, EMA20 нет, Donchian20 нет.

    Но если бы donchian_period=5 — был бы посчитан. Используем custom config.
    """
    history = _make_history(10)
    builder = MarketContextBuilder(
        MarketBuilderConfig(
            atr_period=14,
            donchian_period=5,
            ema_fast_period=5,
            ema_slow_period=8,
            ohlcv_recent_n=5,
        )
    )
    ctx = builder.build(history=history)
    # ATR(14): нужно 15 свечей → "0"
    assert ctx.atr == "0"
    # Donchian(5), EMA(5/8): достаточно
    assert ctx.donchian_high != "0"
    assert ctx.donchian_low != "0"
    assert ctx.ema20 != "0"
    assert ctx.ema50 != "0"


def test_builder_passes_external_market_data() -> None:
    history = _make_history(60)
    builder = MarketContextBuilder()
    ctx = builder.build(
        history=history,
        funding_rate=Decimal("0.0001"),
        oi_change_24h_pct=Decimal("5.5"),
        bid_5=Decimal("80499"),
        ask_5=Decimal("80501"),
        orderbook_imbalance=Decimal("0.12"),
    )
    assert ctx.funding_rate == "0.0001"
    assert ctx.oi_change_24h_pct == "5.5"
    assert ctx.bid_5 == "80499"
    assert ctx.ask_5 == "80501"
    assert ctx.orderbook_imbalance == "0.12"


def test_builder_ohlcv_recent_truncated() -> None:
    history = _make_history(50)
    builder = MarketContextBuilder(MarketBuilderConfig(ohlcv_recent_n=10))
    ctx = builder.build(history=history)
    parsed = json.loads(ctx.ohlcv_recent_json)
    assert len(parsed) == 10
    # Берём именно последние 10
    assert parsed[0]["close"] == str(history[-10].close)
    assert parsed[-1]["close"] == str(history[-1].close)


def test_builder_donchian_uses_high_low() -> None:
    """Проверяем что Donchian реально считается по high/low, а не close."""
    history = _make_history(25)
    builder = MarketContextBuilder()
    ctx = builder.build(history=history)
    # Donchian high = max(c.high) за последние 20 свечей
    expected_high = max(c.high for c in history[-20:])
    expected_low = min(c.low for c in history[-20:])
    assert Decimal(ctx.donchian_high) == expected_high
    assert Decimal(ctx.donchian_low) == expected_low


def test_builder_default_config_when_none() -> None:
    builder = MarketContextBuilder(config=None)
    history = _make_history(60)
    ctx = builder.build(history=history)
    assert ctx.atr != "0"  # config defaults сработали


def test_builder_invalid_atr_period_returns_zero() -> None:
    """ATR period=0 → indicators.atr() бросает ValueError, builder ловит и возвращает '0'."""
    history = _make_history(60)
    builder = MarketContextBuilder(
        MarketBuilderConfig(
            atr_period=0,
            donchian_period=20,
            ema_fast_period=20,
            ema_slow_period=50,
        )
    )
    ctx = builder.build(history=history)
    # ATR упал → "0", остальные индикаторы целы.
    assert ctx.atr == "0"
    assert ctx.donchian_high != "0"
    assert ctx.ema20 != "0"
