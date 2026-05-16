"""Smoke-тесты EdgeHybridStrategy (план 33): ветки A и B."""

from __future__ import annotations

from decimal import Decimal

import pytest

from adapters.bingx.models import Kline
from core.backtest import StrategyContext
from core.risk import RiskEngine
from strategies.edge_hybrid import EdgeHybridConfig, EdgeHybridStrategy


def _cfg() -> EdgeHybridConfig:
    return EdgeHybridConfig.model_validate(
        {
            "symbol": "BTC-USDT",
            "timeframe": "15m",
            "ema_fast": 5,
            "ema_slow": 20,
            "trend_block_pct": 1.5,
            "atr_window": 5,
            "stop_min_pct": 0.3,
            "risk_tier": "B",
            "anchor_ema": 10,
            "entry_k_atr": 2.0,
            "sl_k_atr": 2.0,
            "swing_lookback": 10,
            "sweep_k_atr": 0.25,
            "sl_buf_atr": 0.5,
            "tp_r": 1.5,
            "box_window": 10,
            "box_max_atr": 3.0,
            "strong_body_frac": 0.5,
            "box_tp_r": 1.5,
        }
    )


def _k(t: int, o: str, h: str, low: str, c: str) -> Kline:
    return Kline.model_validate(
        {"time": t, "open": o, "high": h, "low": low, "close": c, "volume": "100"}
    )


def test_no_signal_during_warmup() -> None:
    s = EdgeHybridStrategy(_cfg(), RiskEngine())
    hist = tuple(_k(i, "100", "101", "99", "100") for i in range(6))
    ctx = StrategyContext(
        current_candle=hist[-1], history=hist, equity=Decimal("1000"), open_position=None
    )
    assert s.on_candle_close(ctx) is None


def test_branch_a_buy_far_below_anchor() -> None:
    s = EdgeHybridStrategy(_cfg(), RiskEngine())
    hist = [_k(i, "100", "100.5", "99.5", "100") for i in range(25)]
    hist.append(_k(25, "100", "100", "93", "94"))  # резко ниже якоря, не свип
    ht = tuple(hist)
    ctx = StrategyContext(
        current_candle=ht[-1], history=ht, equity=Decimal("1000"), open_position=None
    )
    o = s.on_candle_close(ctx)
    assert o is not None and o.side == "BUY"


def test_branch_b_buy_on_low_sweep_reclaim() -> None:
    s = EdgeHybridStrategy(_cfg(), RiskEngine())
    hist = [_k(i, "100", "100.5", "99.5", "100") for i in range(24)]
    hist.append(_k(24, "100", "100", "99", "100"))  # свип лоёв + reclaim
    ht = tuple(hist)
    ctx = StrategyContext(
        current_candle=ht[-1], history=ht, equity=Decimal("1000"), open_position=None
    )
    o = s.on_candle_close(ctx)
    assert o is not None and o.side == "BUY"


def test_branch_c_box_breakout_with_volume() -> None:
    s = EdgeHybridStrategy(_cfg(), RiskEngine())
    # Тесный бычий бокс (close>open → up-объём), затем сильный
    # пробой вверх с закрытием за верх бокса.
    hist = [_k(i, "99.8", "100.5", "99.5", "100.0") for i in range(24)]
    hist.append(_k(24, "100.0", "102.0", "100.0", "101.8"))
    ht = tuple(hist)
    ctx = StrategyContext(
        current_candle=ht[-1], history=ht, equity=Decimal("1000"), open_position=None
    )
    o = s.on_candle_close(ctx)
    assert o is not None and o.side == "BUY"


def test_no_trade_in_strong_trend() -> None:
    s = EdgeHybridStrategy(_cfg(), RiskEngine())
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
        EdgeHybridConfig.model_validate(
            {
                "symbol": "BTC-USDT",
                "timeframe": "15m",
                "ema_fast": 20,
                "ema_slow": 20,
                "trend_block_pct": 1.5,
                "atr_window": 5,
                "stop_min_pct": 0.3,
                "anchor_ema": 10,
                "entry_k_atr": 2.0,
                "sl_k_atr": 2.0,
                "swing_lookback": 10,
                "sweep_k_atr": 0.25,
                "sl_buf_atr": 0.5,
                "tp_r": 1.5,
                "box_window": 10,
                "box_max_atr": 3.0,
                "strong_body_frac": 0.5,
                "box_tp_r": 1.5,
            }
        )
