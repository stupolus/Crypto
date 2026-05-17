"""Smoke-тесты ScalpMeanrevStrategy (план 31)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from adapters.bingx.models import Kline
from core.backtest import StrategyContext
from core.risk import RiskEngine
from strategies.scalp_meanrev import ScalpMeanrevConfig, ScalpMeanrevStrategy


def _cfg() -> ScalpMeanrevConfig:
    return ScalpMeanrevConfig.model_validate(
        {
            "symbol": "BTC-USDT",
            "timeframe": "15m",
            "anchor_ema": 10,
            "ema_fast": 5,
            "ema_slow": 20,
            "trend_block_pct": 1.5,
            "atr_window": 5,
            "entry_k_atr": 2.0,
            "sl_k_atr": 2.0,
            "max_hold_bars": 8,
            "stop_min_pct": 0.3,
            "risk_tier": "B",
        }
    )


def _k(t: int, o: str, h: str, low: str, c: str) -> Kline:
    return Kline.model_validate(
        {"time": t, "open": o, "high": h, "low": low, "close": c, "volume": "100"}
    )


def test_no_signal_during_warmup() -> None:
    s = ScalpMeanrevStrategy(_cfg(), RiskEngine())
    hist = tuple(_k(i, "100", "101", "99", "100") for i in range(6))
    ctx = StrategyContext(
        current_candle=hist[-1], history=hist, equity=Decimal("1000"), open_position=None
    )
    assert s.on_candle_close(ctx) is None


def test_buy_when_far_below_anchor_no_trend() -> None:
    s = ScalpMeanrevStrategy(_cfg(), RiskEngine())
    # Боковик ~100 (EMA сжаты), затем резкий провал ниже якоря.
    hist = [_k(i, "100", "100.5", "99.5", "100") for i in range(25)]
    hist.append(_k(25, "100", "100", "93", "94"))  # резко ниже якоря
    ht = tuple(hist)
    ctx = StrategyContext(
        current_candle=ht[-1], history=ht, equity=Decimal("1000"), open_position=None
    )
    o = s.on_candle_close(ctx)
    assert o is not None and o.side == "BUY"


def test_no_trade_in_strong_trend() -> None:
    s = ScalpMeanrevStrategy(_cfg(), RiskEngine())
    # Сильный аптренд → EMA-спред велик → скальп заблокирован.
    hist = [
        _k(i, str(100 + i * 2), str(101 + i * 2), str(99 + i * 2), str(100 + i * 2))
        for i in range(30)
    ]
    ht = tuple(hist)
    ctx = StrategyContext(
        current_candle=ht[-1], history=ht, equity=Decimal("1000"), open_position=None
    )
    assert s.on_candle_close(ctx) is None


def test_config_rejects_fast_geq_slow() -> None:
    with pytest.raises(ValueError, match="ema_fast"):
        ScalpMeanrevConfig.model_validate(
            {
                "symbol": "BTC-USDT",
                "timeframe": "15m",
                "anchor_ema": 10,
                "ema_fast": 20,
                "ema_slow": 20,
                "trend_block_pct": 1.5,
                "atr_window": 5,
                "entry_k_atr": 2.0,
                "sl_k_atr": 2.0,
                "max_hold_bars": 8,
                "stop_min_pct": 0.3,
            }
        )
