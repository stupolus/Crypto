"""Тесты изолированных DOLF-детекторов (план 23 фаза 23.1)."""

from __future__ import annotations

from decimal import Decimal

from core.signals.composite import (
    StaticDeltaProvider,
    StaticFundingProvider,
    StaticLiquidationProvider,
    StaticOpenInterestProvider,
)
from core.signals.dolf_setups import (
    DolfContext,
    SetupSide,
    detect_l2_golden_funding,
    detect_l6_long_from_long_liq,
    detect_s3_nedogora,
    detect_s5_short_from_short_liq,
)
from core.signals.liquidation_sweep import LiquidationBucket

_SYM = "BTC-USDT"
_STEP = 4 * 3_600_000
_T = 1_700_000_000_000


def _ctx(
    *,
    closes: list[float],
    highs: list[float],
    lows: list[float],
    liq: StaticLiquidationProvider | None = None,
    oi: list[float] | None = None,
    funding: Decimal | None = None,
) -> DolfContext:
    oi_series = (
        [(_T - (len(oi) - i) * _STEP, Decimal(str(v))) for i, v in enumerate(oi)] if oi else []
    )
    return DolfContext(
        symbol=_SYM,
        timestamp_ms=_T,
        closes=[Decimal(str(c)) for c in closes],
        highs=[Decimal(str(h)) for h in highs],
        lows=[Decimal(str(low)) for low in lows],
        liq=liq or StaticLiquidationProvider(),
        oi=StaticOpenInterestProvider({_SYM: oi_series}),
        delta=StaticDeltaProvider(),
        funding=StaticFundingProvider({_SYM: funding}),
    )


def _baseline_liq(n: int, each: float) -> dict[int, LiquidationBucket]:
    return {
        _T - (n - i) * _STEP: LiquidationBucket(
            long_volume=Decimal(str(each)), short_volume=Decimal(str(each))
        )
        for i in range(n)
    }


def test_l6_triggers_on_long_liq_spike_and_new_low() -> None:
    buckets = _baseline_liq(30, 1000.0)
    buckets[_T] = LiquidationBucket(long_volume=Decimal("500000"), short_volume=Decimal("1000"))
    liq = StaticLiquidationProvider({_SYM: buckets})
    lows = [100.0] * 20 + [90.0]  # последний — новый минимум
    r = detect_l6_long_from_long_liq(
        _ctx(closes=[100.0] * 21, highs=[110.0] * 21, lows=lows, liq=liq)
    )
    assert r.triggered and r.side is SetupSide.LONG


def test_l6_no_trigger_without_spike() -> None:
    buckets = _baseline_liq(30, 1000.0)
    buckets[_T] = LiquidationBucket(long_volume=Decimal("1500"), short_volume=Decimal("100"))
    liq = StaticLiquidationProvider({_SYM: buckets})
    lows = [100.0] * 20 + [90.0]
    r = detect_l6_long_from_long_liq(
        _ctx(closes=[100.0] * 21, highs=[110.0] * 21, lows=lows, liq=liq)
    )
    assert not r.triggered


def test_s5_triggers_on_short_liq_new_high_oi_falling() -> None:
    buckets = _baseline_liq(30, 1000.0)
    buckets[_T] = LiquidationBucket(long_volume=Decimal("1000"), short_volume=Decimal("400000"))
    liq = StaticLiquidationProvider({_SYM: buckets})
    highs = [100.0] * 20 + [120.0]  # новый хай
    r = detect_s5_short_from_short_liq(
        _ctx(
            closes=[100.0] * 21,
            highs=highs,
            lows=[90.0] * 21,
            liq=liq,
            oi=[200.0, 190.0, 180.0, 170.0, 160.0, 150.0],
        )
    )
    assert r.triggered and r.side is SetupSide.SHORT


def test_l2_golden_funding_long() -> None:
    r = detect_l2_golden_funding(
        _ctx(
            closes=[100.0, 105.0, 110.0],
            highs=[110.0] * 3,
            lows=[95.0] * 3,
            oi=[100.0, 120.0, 140.0],
            funding=Decimal("-0.015"),
        )
    )
    assert r.triggered and r.side is SetupSide.LONG


def test_l2_no_trigger_when_funding_not_negative_enough() -> None:
    r = detect_l2_golden_funding(
        _ctx(
            closes=[100.0, 105.0, 110.0],
            highs=[110.0] * 3,
            lows=[95.0] * 3,
            oi=[100.0, 120.0, 140.0],
            funding=Decimal("-0.002"),
        )
    )
    assert not r.triggered


def test_s3_nedogora_short() -> None:
    # цена новый хай, OI последний << прошлого пика (дивергенция)
    r = detect_s3_nedogora(
        _ctx(
            closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 110.0],
            highs=[110.0] * 7,
            lows=[95.0] * 7,
            oi=[100.0, 200.0, 180.0, 160.0, 150.0, 140.0, 120.0],
        )
    )
    assert r.triggered and r.side is SetupSide.SHORT


def test_s3_no_trigger_when_oi_confirms() -> None:
    r = detect_s3_nedogora(
        _ctx(
            closes=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 110.0],
            highs=[110.0] * 7,
            lows=[95.0] * 7,
            oi=[100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0],
        )
    )
    assert not r.triggered
