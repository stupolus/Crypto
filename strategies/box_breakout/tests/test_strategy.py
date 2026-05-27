"""Unit-тесты BoxBreakoutStrategy (логика, не edge — edge на WF)."""

from __future__ import annotations

from decimal import Decimal

from adapters.bingx.models import Kline
from core.backtest import StrategyContext
from core.risk import RiskEngine
from strategies.box_breakout import BoxBreakoutStrategy
from strategies.box_breakout.config import BoxBreakoutConfig

_STEP = 900_000


def _cfg(**ov: object) -> BoxBreakoutConfig:
    base: dict[str, object] = {
        "symbol": "BTC-USDT",
        "timeframe": "15m",
        "box_n": 10,
        "box_max_width_pct": 5.0,
        "vol_sma_window": 10,
        "breakout_vol_mult": 1.5,
        "atr_window": 5,
        "atr_sl_mult": 1.0,
        "stop_min_pct": 0.3,
        "tp_r": 1.8,
        "risk_tier": "B",
        "direction_bias": "both",
    }
    base.update(ov)
    return BoxBreakoutConfig.model_validate(base)


def _k(t: int, o: float, h: float, lo: float, c: float, v: float = 100.0) -> Kline:
    return Kline.model_validate(
        {
            "time": t,
            "open": str(o),
            "high": str(h),
            "low": str(lo),
            "close": str(c),
            "volume": str(v),
        }
    )


def _box(n: int, *, bullish: bool, vol: float = 100.0) -> list[Kline]:
    """n узких баров вокруг 100 (width <5%); bias по знаку close-open."""
    out = []
    for i in range(n):
        if bullish:
            o, c = 99.8, 100.2  # close>open
        else:
            o, c = 100.2, 99.8
        out.append(_k(i * _STEP, o, 100.5, 99.5, c, vol))
    return out


def _ctx(hist: list[Kline]) -> StrategyContext:
    return StrategyContext(
        current_candle=hist[-1],
        history=tuple(hist),
        equity=Decimal("10000"),
        open_position=None,
    )


def test_warmup_returns_none() -> None:
    s = BoxBreakoutStrategy(_cfg(), RiskEngine())
    assert s.on_candle_close(_ctx(_box(3, bullish=True))) is None


def test_no_breakout_inside_box_returns_none() -> None:
    s = BoxBreakoutStrategy(_cfg(), RiskEngine())
    hist = _box(11, bullish=True)  # последняя свеча внутри бокса
    assert s.on_candle_close(_ctx(hist)) is None


def test_long_breakout_emits_buy() -> None:
    s = BoxBreakoutStrategy(_cfg(), RiskEngine())
    hist = _box(11, bullish=True)
    # свеча-пробой: close выше hi (100.5), объём ≥1.5×средн.
    hist[-1] = _k(11 * _STEP, 100.4, 103.0, 100.3, 102.5, v=300.0)
    order = s.on_candle_close(_ctx(hist))
    assert order is not None
    assert order.side == "BUY"
    assert order.attached_take_profit is not None and order.attached_stop_loss is not None
    assert order.attached_stop_loss < Decimal("102.5") < order.attached_take_profit


def test_breakout_weak_volume_blocked() -> None:
    s = BoxBreakoutStrategy(_cfg(), RiskEngine())
    hist = _box(11, bullish=True, vol=100.0)
    hist[-1] = _k(11 * _STEP, 100.4, 103.0, 100.3, 102.5, v=100.0)  # объём не выше
    assert s.on_candle_close(_ctx(hist)) is None


def test_wide_box_not_consolidation_blocked() -> None:
    s = BoxBreakoutStrategy(_cfg(), RiskEngine())
    # широкий бокс: low 80 hi 120 → width >5%
    hist = [_k(i * _STEP, 100, 120, 80, 101, 100) for i in range(11)]
    hist[-1] = _k(11 * _STEP, 101, 130, 100, 125, 300)
    assert s.on_candle_close(_ctx(hist)) is None


def test_direction_bias_long_only_blocks_short() -> None:
    s = BoxBreakoutStrategy(_cfg(direction_bias="long_only"), RiskEngine())
    hist = _box(11, bullish=False)
    hist[-1] = _k(11 * _STEP, 99.6, 99.7, 97.0, 97.5, v=300.0)  # пробой вниз
    assert s.on_candle_close(_ctx(hist)) is None
