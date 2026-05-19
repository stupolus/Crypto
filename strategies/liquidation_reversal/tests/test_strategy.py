"""Unit-тесты LiquidationReversalStrategy на Static-провайдерах.

Проверяем логику композита (план 21 A1/A2), не edge — edge на бэктесте.
"""

from __future__ import annotations

from decimal import Decimal

from adapters.bingx.models import Kline
from core.backtest import StrategyContext
from core.risk import RiskEngine
from core.signals import (
    StaticDeltaProvider,
    StaticFundingProvider,
    StaticLiquidationProvider,
    StaticOpenInterestProvider,
)
from core.signals.liquidation_sweep import LiquidationBucket
from strategies.liquidation_reversal import LiquidationReversalStrategy
from strategies.liquidation_reversal.config import LiqReversalConfig

_STEP = 900_000  # 15m


def _cfg(**ov: object) -> LiqReversalConfig:
    base: dict[str, object] = {
        "symbol": "BTC-USDT",
        "timeframe": "15m",
        "level_n": 5,
        "liq_spike_min": 5.0,
        "liq_min_baseline_usd": 10.0,
        "liq_baseline_n": 3,
        "cycle_wait_bars": 1,
        "oi_lookback": 3,
        "oi_rise_pct": 3.0,
        "oi_fall_pct": 3.0,
        "cvd_lookback": 4,
        "funding_short_block": -0.015,
        "stop_min_pct": 0.5,
        "tp1_r_multiple": 3.0,
        "risk_tier": "B",
        "direction_bias": "both",
    }
    base.update(ov)
    return LiqReversalConfig.model_validate(base)


def _k(t: int, o: str, h: str, lo: str, c: str) -> Kline:
    return Kline.model_validate(
        {"time": t, "open": o, "high": h, "low": lo, "close": c, "volume": "100"}
    )


def _bucket(lng: str, sht: str) -> LiquidationBucket:
    return LiquidationBucket(long_volume=Decimal(lng), short_volume=Decimal(sht))


def _history(n: int, base: float = 100.0) -> list[Kline]:
    """n свечей в коридоре base±1, шаг 15m."""
    return [_k(i * _STEP, str(base), f"{base + 1}", f"{base - 1}", str(base)) for i in range(n)]


def _oi_rising(ts: int) -> list[tuple[int, Decimal]]:
    # 10 точек растущего OI до ts
    return [(ts - (10 - i) * _STEP, Decimal(str(1000 + i * 80))) for i in range(10)]


def _oi_falling(ts: int) -> list[tuple[int, Decimal]]:
    return [(ts - (10 - i) * _STEP, Decimal(str(2000 - i * 80))) for i in range(10)]


def test_no_signal_during_warmup() -> None:
    s = LiquidationReversalStrategy(_cfg(), RiskEngine())
    hist = tuple(_history(3))
    ctx = StrategyContext(
        current_candle=hist[-1], history=hist, equity=Decimal("10000"), open_position=None
    )
    assert s.on_candle_close(ctx) is None


def test_a1_long_full_setup_emits_order() -> None:
    """Long-ликвидации на лоях + цикл + OI не падает + CVD вверх → BUY."""
    n = 7
    hist = _history(n)
    trig_ts = n * _STEP  # ts свечи-триггера (close ниже donchian low)
    # Триггер-свеча: close=90 ≤ donchian_low(95-1? hist low=99) → 90 < 99
    trigger = _k(trig_ts, "100", "100", "88", "90")
    confirm_ts = (n + 1) * _STEP
    confirm = _k(confirm_ts, "90", "92", "89", "91")

    liq = StaticLiquidationProvider(
        {
            "BTC-USDT": {
                trig_ts - 3 * _STEP: _bucket("100", "0"),
                trig_ts - 2 * _STEP: _bucket("100", "0"),
                trig_ts - _STEP: _bucket("100", "0"),
                trig_ts: _bucket("50000", "0"),  # 500x baseline, long-share 1.0 → BUY
            }
        }
    )
    oi = StaticOpenInterestProvider({"BTC-USDT": _oi_rising(confirm_ts)})
    delta = StaticDeltaProvider(
        {"BTC-USDT": [(confirm_ts - 3 * _STEP, Decimal("-5")), (confirm_ts, Decimal("20"))]}
    )
    s = LiquidationReversalStrategy(
        _cfg(),
        RiskEngine(),
        liquidation_provider=liq,
        oi_provider=oi,
        delta_provider=delta,
    )

    # Bar 1: триггер — фиксирует pending setup, ордер не отдаёт.
    ctx1 = StrategyContext(
        current_candle=trigger,
        history=(*hist, trigger),
        equity=Decimal("10000"),
        open_position=None,
    )
    assert s.on_candle_close(ctx1) is None

    # Bar 2: цикл завершён (cycle_wait_bars=1) + подтверждение → BUY.
    ctx2 = StrategyContext(
        current_candle=confirm,
        history=(*hist, trigger, confirm),
        equity=Decimal("10000"),
        open_position=None,
    )
    order = s.on_candle_close(ctx2)
    assert order is not None
    assert order.side == "BUY"
    assert order.attached_stop_loss is not None
    assert order.attached_stop_loss < Decimal("91")
    assert order.attached_take_profit is not None
    assert order.attached_take_profit > Decimal("91")


def test_a1_blocked_when_cvd_not_up() -> None:
    """Тот же setup, но CVD вниз → нет входа."""
    n = 7
    hist = _history(n)
    trig_ts = n * _STEP
    trigger = _k(trig_ts, "100", "100", "88", "90")
    confirm_ts = (n + 1) * _STEP
    confirm = _k(confirm_ts, "90", "92", "89", "91")
    liq = StaticLiquidationProvider(
        {
            "BTC-USDT": {
                trig_ts - 3 * _STEP: _bucket("100", "0"),
                trig_ts - 2 * _STEP: _bucket("100", "0"),
                trig_ts - _STEP: _bucket("100", "0"),
                trig_ts: _bucket("50000", "0"),
            }
        }
    )
    oi = StaticOpenInterestProvider({"BTC-USDT": _oi_rising(confirm_ts)})
    delta = StaticDeltaProvider(
        {"BTC-USDT": [(confirm_ts - 3 * _STEP, Decimal("20")), (confirm_ts, Decimal("-5"))]}
    )
    s = LiquidationReversalStrategy(
        _cfg(), RiskEngine(), liquidation_provider=liq, oi_provider=oi, delta_provider=delta
    )
    s.on_candle_close(
        StrategyContext(
            current_candle=trigger,
            history=(*hist, trigger),
            equity=Decimal("10000"),
            open_position=None,
        )
    )
    assert (
        s.on_candle_close(
            StrategyContext(
                current_candle=confirm,
                history=(*hist, trigger, confirm),
                equity=Decimal("10000"),
                open_position=None,
            )
        )
        is None
    )


def test_a2_short_requires_falling_oi() -> None:
    """Short-ликвидации на хаях, но OI растёт → жёсткий gate блокирует."""
    n = 7
    hist = _history(n)
    trig_ts = n * _STEP
    # close выше donchian_high (hist high=101) → 110 > 101
    trigger = _k(trig_ts, "100", "112", "100", "110")
    confirm_ts = (n + 1) * _STEP
    confirm = _k(confirm_ts, "110", "111", "108", "109")
    liq = StaticLiquidationProvider(
        {
            "BTC-USDT": {
                trig_ts - 3 * _STEP: _bucket("0", "100"),
                trig_ts - 2 * _STEP: _bucket("0", "100"),
                trig_ts - _STEP: _bucket("0", "100"),
                trig_ts: _bucket("0", "50000"),  # short-share 1.0 → SELL
            }
        }
    )
    oi_rising = StaticOpenInterestProvider({"BTC-USDT": _oi_rising(confirm_ts)})
    delta = StaticDeltaProvider(
        {"BTC-USDT": [(confirm_ts - 3 * _STEP, Decimal("5")), (confirm_ts, Decimal("-20"))]}
    )
    s = LiquidationReversalStrategy(
        _cfg(),
        RiskEngine(),
        liquidation_provider=liq,
        oi_provider=oi_rising,
        delta_provider=delta,
    )
    s.on_candle_close(
        StrategyContext(
            current_candle=trigger,
            history=(*hist, trigger),
            equity=Decimal("10000"),
            open_position=None,
        )
    )
    # OI растёт → шорт-gate НЕ пройден.
    assert (
        s.on_candle_close(
            StrategyContext(
                current_candle=confirm,
                history=(*hist, trigger, confirm),
                equity=Decimal("10000"),
                open_position=None,
            )
        )
        is None
    )


def test_a2_short_passes_on_falling_oi() -> None:
    """Тот же A2, но OI падает + CVD вниз → SELL."""
    n = 7
    hist = _history(n)
    trig_ts = n * _STEP
    trigger = _k(trig_ts, "100", "112", "100", "110")
    confirm_ts = (n + 1) * _STEP
    confirm = _k(confirm_ts, "110", "111", "108", "109")
    liq = StaticLiquidationProvider(
        {
            "BTC-USDT": {
                trig_ts - 3 * _STEP: _bucket("0", "100"),
                trig_ts - 2 * _STEP: _bucket("0", "100"),
                trig_ts - _STEP: _bucket("0", "100"),
                trig_ts: _bucket("0", "50000"),
            }
        }
    )
    oi = StaticOpenInterestProvider({"BTC-USDT": _oi_falling(confirm_ts)})
    delta = StaticDeltaProvider(
        {"BTC-USDT": [(confirm_ts - 3 * _STEP, Decimal("5")), (confirm_ts, Decimal("-20"))]}
    )
    fund = StaticFundingProvider({"BTC-USDT": Decimal("0.0")})
    s = LiquidationReversalStrategy(
        _cfg(),
        RiskEngine(),
        liquidation_provider=liq,
        oi_provider=oi,
        delta_provider=delta,
        funding_provider=fund,
    )
    s.on_candle_close(
        StrategyContext(
            current_candle=trigger,
            history=(*hist, trigger),
            equity=Decimal("10000"),
            open_position=None,
        )
    )
    order = s.on_candle_close(
        StrategyContext(
            current_candle=confirm,
            history=(*hist, trigger, confirm),
            equity=Decimal("10000"),
            open_position=None,
        )
    )
    assert order is not None
    assert order.side == "SELL"


def test_oi_gate_disabled_allows_short_despite_rising_oi() -> None:
    """oi_gate_enabled=False → шорт проходит даже при растущем OI."""
    n = 7
    hist = _history(n)
    trig_ts = n * _STEP
    trigger = _k(trig_ts, "100", "112", "100", "110")
    confirm_ts = (n + 1) * _STEP
    confirm = _k(confirm_ts, "110", "111", "108", "109")
    liq = StaticLiquidationProvider(
        {
            "BTC-USDT": {
                trig_ts - 3 * _STEP: _bucket("0", "100"),
                trig_ts - 2 * _STEP: _bucket("0", "100"),
                trig_ts - _STEP: _bucket("0", "100"),
                trig_ts: _bucket("0", "50000"),
            }
        }
    )
    oi_rising = StaticOpenInterestProvider({"BTC-USDT": _oi_rising(confirm_ts)})
    delta = StaticDeltaProvider(
        {"BTC-USDT": [(confirm_ts - 3 * _STEP, Decimal("5")), (confirm_ts, Decimal("-20"))]}
    )
    fund = StaticFundingProvider({"BTC-USDT": Decimal("0.0")})
    s = LiquidationReversalStrategy(
        _cfg(oi_gate_enabled=False),
        RiskEngine(),
        liquidation_provider=liq,
        oi_provider=oi_rising,
        delta_provider=delta,
        funding_provider=fund,
    )
    s.on_candle_close(
        StrategyContext(
            current_candle=trigger,
            history=(*hist, trigger),
            equity=Decimal("10000"),
            open_position=None,
        )
    )
    order = s.on_candle_close(
        StrategyContext(
            current_candle=confirm,
            history=(*hist, trigger, confirm),
            equity=Decimal("10000"),
            open_position=None,
        )
    )
    assert order is not None
    assert order.side == "SELL"


def test_no_sweep_no_setup() -> None:
    """Нет ликвидаций → нет setup, нет ордера."""
    n = 7
    hist = _history(n)
    trig_ts = n * _STEP
    trigger = _k(trig_ts, "100", "100", "88", "90")
    s = LiquidationReversalStrategy(_cfg(), RiskEngine())  # пустые провайдеры
    assert (
        s.on_candle_close(
            StrategyContext(
                current_candle=trigger,
                history=(*hist, trigger),
                equity=Decimal("10000"),
                open_position=None,
            )
        )
        is None
    )


def test_atr_stop_widens_distance() -> None:
    """Улучшение №1: ATR-стоп не уже ATR*mult (расширяет фикс-floor)."""
    s = LiquidationReversalStrategy(
        _cfg(stop_min_pct=0.1, stop_atr_period=3, stop_atr_mult=2.0),
        RiskEngine(),
    )
    # свечи с TR≈2 (high-low=2) → ATR≈2; entry 100 → atr_dist≈4
    hist = [_k(i * _STEP, "100", "101", "99", "100") for i in range(6)]
    entry = Decimal("100")
    stop = s._compute_stop(entry, "BUY", Decimal("99.95"), hist)
    fixed = entry - entry * Decimal("0.001")  # stop_min_pct=0.1%
    assert (entry - stop) > (entry - fixed)  # ATR расширил
    assert (entry - stop) >= Decimal("3.5")  # ≈ ATR(2)*2


def test_reversal_exit_closes_long_on_cvd_oi_down() -> None:
    """Улучшение №2: лонг закрывается при CVD↓ и OI↓."""
    from core.backtest import OpenPosition

    ts = 20 * _STEP
    delta = StaticDeltaProvider(
        {"BTC-USDT": [(ts - 3 * _STEP, Decimal("50")), (ts, Decimal("-30"))]}
    )
    oi = StaticOpenInterestProvider({"BTC-USDT": _oi_falling(ts)})
    s = LiquidationReversalStrategy(
        _cfg(reversal_exit_enabled=True),
        RiskEngine(),
        oi_provider=oi,
        delta_provider=delta,
    )
    pos = OpenPosition(
        entry_price=Decimal("100"),
        quantity=Decimal("0.5"),
        side="BUY",
        stop_price=Decimal("95"),
        take_profit_price=None,
        entry_time_ms=ts - 5 * _STEP,
    )
    order = s.on_candle_close(
        StrategyContext(
            current_candle=_k(ts, "100", "101", "99", "100"),
            history=tuple(_history(25)),
            equity=Decimal("10000"),
            open_position=pos,
        )
    )
    assert order is not None
    assert order.side == "SELL"
    assert order.quantity == Decimal("0.5")


def test_reversal_exit_disabled_by_default() -> None:
    """Без флага позицию ведёт биржевой SL/TP (return None)."""
    from core.backtest import OpenPosition

    ts = 20 * _STEP
    s = LiquidationReversalStrategy(_cfg(), RiskEngine())
    pos = OpenPosition(
        entry_price=Decimal("100"),
        quantity=Decimal("0.5"),
        side="BUY",
        stop_price=Decimal("95"),
        take_profit_price=None,
        entry_time_ms=ts - _STEP,
    )
    assert (
        s.on_candle_close(
            StrategyContext(
                current_candle=_k(ts, "100", "101", "99", "100"),
                history=tuple(_history(25)),
                equity=Decimal("10000"),
                open_position=pos,
            )
        )
        is None
    )


def test_protocol_compliance() -> None:
    from core.backtest import Strategy

    assert isinstance(LiquidationReversalStrategy(_cfg(), RiskEngine()), Strategy)
