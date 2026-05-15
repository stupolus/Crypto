"""Smoke unit-тесты ``UsSessionBreakoutStrategy``."""

from __future__ import annotations

from decimal import Decimal

from adapters.bingx.models import Kline
from core.backtest import StrategyContext
from core.risk import RiskEngine
from strategies.us_session_breakout import UsSessionBreakoutStrategy
from strategies.us_session_breakout.config import UsSessionConfig


def _make_cfg() -> UsSessionConfig:
    return UsSessionConfig.model_validate(
        {
            "symbol": "BTC-USDT",
            "timeframe": "15m",
            "asian_start_hour_utc": 0,
            "asian_end_hour_utc": 13,
            "us_start_hour_utc": 13,
            "us_end_hour_utc": 15,
            "eod_close_hour_utc": 23,
            "min_range_pct": 0.5,
            "max_range_pct": 5.0,
            "stop_min_pct": 0.5,
            "tp1_r_multiple": 1.5,
            "risk_tier": "B",
        }
    )


def _kline(ts: int, open_: str, high: str, low: str, close: str) -> Kline:
    return Kline.model_validate(
        {
            "time": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": "100",
        }
    )


def test_no_signal_during_asian_window() -> None:
    strategy = UsSessionBreakoutStrategy(_make_cfg(), RiskEngine())
    # 2024-01-01 00:00:00 UTC
    ts = 1704067200000
    candle = _kline(ts, "100", "101", "99", "100")
    ctx = StrategyContext(
        current_candle=candle,
        history=(candle,),
        equity=Decimal("1000"),
        open_position=None,
    )
    assert strategy.on_candle_close(ctx) is None


def test_protocol_compliance() -> None:
    from core.backtest import Strategy

    strategy = UsSessionBreakoutStrategy(_make_cfg(), RiskEngine())
    assert isinstance(strategy, Strategy)


def test_config_rejects_misaligned_session_boundaries() -> None:
    """asian_end != us_start → должна быть ValueError."""
    import pytest

    with pytest.raises(ValueError, match="asian_end_hour_utc"):
        UsSessionConfig.model_validate(
            {
                "symbol": "BTC-USDT",
                "timeframe": "15m",
                "asian_start_hour_utc": 0,
                "asian_end_hour_utc": 12,
                "us_start_hour_utc": 13,
                "us_end_hour_utc": 15,
                "eod_close_hour_utc": 23,
                "min_range_pct": 0.5,
                "max_range_pct": 5.0,
                "stop_min_pct": 0.5,
                "tp1_r_multiple": 1.5,
                "risk_tier": "B",
            }
        )


def test_breakout_long_after_asian_range() -> None:
    """E2E: накапливаем Asian range, затем close > asian_high в US window → BUY."""
    strategy = UsSessionBreakoutStrategy(_make_cfg(), RiskEngine())
    base = 1704067200000  # 2024-01-01 00:00 UTC

    # Asian session: свечи каждый час 0..12, range [99..101]
    history: list[Kline] = []
    last_ctx_signal = None
    for h in range(13):
        c = _kline(
            base + h * 3600000,
            "100",
            "101",
            "99",
            "100",
        )
        history.append(c)
        ctx = StrategyContext(
            current_candle=c,
            history=tuple(history),
            equity=Decimal("1000"),
            open_position=None,
        )
        result = strategy.on_candle_close(ctx)
        assert result is None, f"hour {h} should be no-signal"

    # US window candle: close > asian_high (101)
    breakout_candle = _kline(
        base + 13 * 3600000,
        "101",
        "102.5",
        "100.5",
        "102",
    )
    history.append(breakout_candle)
    ctx = StrategyContext(
        current_candle=breakout_candle,
        history=tuple(history),
        equity=Decimal("1000"),
        open_position=None,
    )
    last_ctx_signal = strategy.on_candle_close(ctx)
    assert last_ctx_signal is not None
    assert last_ctx_signal.side == "BUY"
    assert last_ctx_signal.attached_stop_loss == Decimal("99")  # asian_low
