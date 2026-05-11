"""Smoke unit-тесты ``TrendEmaStrategy``."""

from __future__ import annotations

from decimal import Decimal

import pytest

from adapters.bingx.models import Kline
from core.backtest import StrategyContext
from core.risk import RiskEngine
from strategies.trend_ema_4h import TrendEmaConfig, TrendEmaStrategy


def _cfg() -> TrendEmaConfig:
    return TrendEmaConfig.model_validate(
        {
            "symbol": "BTC-USDT",
            "timeframe": "4h",
            "ema_fast": 5,
            "ema_slow": 10,
            "atr_window": 5,
            "sl_atr_multiplier": 1.5,
            "min_ema_spread_pct": 0.2,
            "stop_min_pct": 0.5,
            "tp1_r_multiple": 1.5,
            "risk_tier": "B",
        }
    )


def _kline(t: int, o: str, h: str, low: str, c: str) -> Kline:
    return Kline.model_validate(
        {"time": t, "open": o, "high": h, "low": low, "close": c, "volume": "100"}
    )


def test_no_signal_during_warmup() -> None:
    strategy = TrendEmaStrategy(_cfg(), RiskEngine())
    history = tuple(_kline(i, "100", "101", "99", "100") for i in range(5))
    ctx = StrategyContext(
        current_candle=history[-1],
        history=history,
        equity=Decimal("1000"),
        open_position=None,
    )
    assert strategy.on_candle_close(ctx) is None


def test_config_rejects_fast_geq_slow() -> None:
    with pytest.raises(ValueError, match="ema_fast"):
        TrendEmaConfig.model_validate(
            {
                "symbol": "BTC-USDT",
                "timeframe": "4h",
                "ema_fast": 50,
                "ema_slow": 50,
                "atr_window": 14,
                "sl_atr_multiplier": 1.5,
                "min_ema_spread_pct": 0.2,
                "stop_min_pct": 0.5,
                "tp1_r_multiple": 1.5,
                "risk_tier": "B",
            }
        )


def test_strategy_protocol_compliance() -> None:
    from core.backtest import Strategy

    s = TrendEmaStrategy(_cfg(), RiskEngine())
    assert isinstance(s, Strategy)
