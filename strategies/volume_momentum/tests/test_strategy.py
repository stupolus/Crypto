"""Smoke-тесты VolumeMomentumStrategy (план 28)."""

from __future__ import annotations

from decimal import Decimal

from adapters.bingx.models import Kline
from core.backtest import StrategyContext
from core.risk import RiskEngine
from strategies.volume_momentum import VolumeMomentumConfig, VolumeMomentumStrategy


def _cfg() -> VolumeMomentumConfig:
    return VolumeMomentumConfig.model_validate(
        {
            "symbol": "BTC-USDT",
            "timeframe": "4h",
            "vol_n": 5,
            "vol_mult": 2.5,
            "atr_window": 5,
            "sl_atr_multiplier": 1.5,
            "stop_min_pct": 0.5,
            "tp1_r_multiple": 2.0,
            "risk_tier": "B",
        }
    )


def _k(t: int, o: str, h: str, low: str, c: str, v: str) -> Kline:
    return Kline.model_validate(
        {"time": t, "open": o, "high": h, "low": low, "close": c, "volume": v}
    )


def test_no_signal_during_warmup() -> None:
    s = VolumeMomentumStrategy(_cfg(), RiskEngine())
    hist = tuple(_k(i, "100", "101", "99", "100", "100") for i in range(4))
    ctx = StrategyContext(
        current_candle=hist[-1], history=hist, equity=Decimal("1000"), open_position=None
    )
    assert s.on_candle_close(ctx) is None


def test_volume_spike_bullish_triggers_buy() -> None:
    s = VolumeMomentumStrategy(_cfg(), RiskEngine())
    hist = [_k(i, "100", "101", "99", "100", "100") for i in range(10)]
    # всплеск объёма ×5 + бычья свеча
    hist.append(_k(10, "100", "106", "99", "105", "600"))
    ht = tuple(hist)
    ctx = StrategyContext(
        current_candle=ht[-1], history=ht, equity=Decimal("1000"), open_position=None
    )
    o = s.on_candle_close(ctx)
    assert o is not None and o.side == "BUY"


def test_no_trigger_without_volume_spike() -> None:
    s = VolumeMomentumStrategy(_cfg(), RiskEngine())
    hist = [_k(i, "100", "101", "99", "100", "100") for i in range(10)]
    hist.append(_k(10, "100", "106", "99", "105", "110"))  # объём почти средний
    ht = tuple(hist)
    ctx = StrategyContext(
        current_candle=ht[-1], history=ht, equity=Decimal("1000"), open_position=None
    )
    assert s.on_candle_close(ctx) is None
