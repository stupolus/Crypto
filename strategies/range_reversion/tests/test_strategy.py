"""Smoke unit-тесты RangeReversionStrategy (план 25)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from adapters.bingx.models import Kline
from core.backtest import StrategyContext
from core.risk import RiskEngine
from strategies.range_reversion import RangeReversionConfig, RangeReversionStrategy


def _cfg() -> RangeReversionConfig:
    return RangeReversionConfig.model_validate(
        {
            "symbol": "BTC-USDT",
            "timeframe": "4h",
            "channel_n": 5,
            "ema_fast": 3,
            "ema_slow": 6,
            "range_max_spread_pct": 1.0,
            "band_buffer_pct": 0.5,
            "atr_window": 5,
            "sl_atr_multiplier": 1.0,
            "stop_min_pct": 0.5,
            "tp1_r_multiple": 2.0,
            "risk_tier": "B",
        }
    )


def _k(t: int, o: str, h: str, low: str, c: str) -> Kline:
    return Kline.model_validate(
        {"time": t, "open": o, "high": h, "low": low, "close": c, "volume": "100"}
    )


def test_no_signal_during_warmup() -> None:
    s = RangeReversionStrategy(_cfg(), RiskEngine())
    hist = tuple(_k(i, "100", "101", "99", "100") for i in range(5))
    ctx = StrategyContext(
        current_candle=hist[-1], history=hist, equity=Decimal("1000"), open_position=None
    )
    assert s.on_candle_close(ctx) is None


def test_buy_near_lower_band_in_range() -> None:
    s = RangeReversionStrategy(_cfg(), RiskEngine())
    # Боковик ~100 (EMA сжаты), затем тык в нижнюю границу канала.
    hist = [_k(i, "100", "101", "99", "100") for i in range(20)]
    hist.append(_k(20, "100", "100", "98.5", "99.0"))  # close у lo
    ht = tuple(hist)
    ctx = StrategyContext(
        current_candle=ht[-1], history=ht, equity=Decimal("1000"), open_position=None
    )
    order = s.on_candle_close(ctx)
    assert order is not None and order.side == "BUY"
    sl = order.attached_stop_loss
    tp = order.attached_take_profit
    assert sl is not None and tp is not None
    assert sl < tp


def test_no_trade_when_trending() -> None:
    s = RangeReversionStrategy(_cfg(), RiskEngine())
    # Сильный аптренд → EMA-спред велик → не боковик → нет входа.
    hist = [_k(i, str(100 + i), str(101 + i), str(99 + i), str(100 + i)) for i in range(21)]
    ht = tuple(hist)
    ctx = StrategyContext(
        current_candle=ht[-1], history=ht, equity=Decimal("1000"), open_position=None
    )
    assert s.on_candle_close(ctx) is None


def test_config_rejects_fast_geq_slow() -> None:
    with pytest.raises(ValueError, match="ema_fast"):
        RangeReversionConfig.model_validate(
            {
                "symbol": "BTC-USDT",
                "timeframe": "4h",
                "channel_n": 5,
                "ema_fast": 6,
                "ema_slow": 6,
                "range_max_spread_pct": 1.0,
                "band_buffer_pct": 0.5,
                "atr_window": 5,
                "sl_atr_multiplier": 1.0,
                "stop_min_pct": 0.5,
                "tp1_r_multiple": 2.0,
            }
        )
