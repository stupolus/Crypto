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
    ALL_DETECTORS,
    DolfContext,
    SetupSide,
    detect_l1_trend_start,
    detect_l2_golden_funding,
    detect_l3_oi_drop_flat_price,
    detect_l4_trend_continuation,
    detect_l5_shortodon,
    detect_l6_long_from_long_liq,
    detect_s1_oi_drop_after_pump,
    detect_s2_price_oi_divergence,
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
    volumes: list[float] | None = None,
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
        volumes=[Decimal(str(v)) for v in (volumes or [1.0] * len(closes))],
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


def test_l1_trend_start_long() -> None:
    # price +5%, OI +30%, vol +40% за окно 6 → ΔOI,Δvol > Δprice
    r = detect_l1_trend_start(
        _ctx(
            closes=[100.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            highs=[105.0] * 7,
            lows=[99.0] * 7,
            oi=[100.0, 105.0, 112.0, 120.0, 125.0, 128.0, 130.0],
            volumes=[100.0, 100.0, 110.0, 120.0, 130.0, 135.0, 140.0],
        )
    )
    assert r.triggered and r.side is SetupSide.LONG


def test_l1_no_trigger_when_oi_lags_price() -> None:
    r = detect_l1_trend_start(
        _ctx(
            closes=[100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0],
            highs=[160.0] * 7,
            lows=[99.0] * 7,
            oi=[100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 101.0],
            volumes=[100.0] * 7,
        )
    )
    assert not r.triggered


def test_l3_oi_drop_flat_price_long() -> None:
    r = detect_l3_oi_drop_flat_price(
        _ctx(
            closes=[100.0] * 12,
            highs=[101.0] * 12,
            lows=[99.0] * 12,
            oi=[100.0, 140.0, 160.0, 170.0, 165.0, 150.0, 145.0, 140.0, 138.0, 136.0, 134.0, 132.0],
        )
    )
    assert r.triggered and r.side is SetupSide.LONG


def test_l4_trend_continuation_long() -> None:
    r = detect_l4_trend_continuation(
        _ctx(
            closes=[110.0, 109.0, 108.0, 107.0, 106.0, 105.0, 104.0],
            highs=[111.0] * 7,
            lows=[103.0] * 7,
            oi=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        )
    )
    assert r.triggered and r.side is SetupSide.LONG


def test_l5_shortodon_long() -> None:
    r = detect_l5_shortodon(
        _ctx(
            closes=[110.0, 108.0, 106.0, 104.0, 102.0, 100.0, 98.0],
            highs=[111.0] * 7,
            lows=[97.0] * 7,
            oi=[100.0, 110.0, 120.0, 130.0, 140.0, 150.0],
            volumes=[100.0, 120.0, 140.0, 160.0, 180.0, 200.0, 220.0],
        )
    )
    assert r.triggered and r.side is SetupSide.LONG


def test_s1_oi_drop_after_pump_short() -> None:
    r = detect_s1_oi_drop_after_pump(
        _ctx(
            closes=[
                100.0,
                130.0,
                150.0,
                160.0,
                158.0,
                155.0,
                152.0,
                150.0,
                148.0,
                146.0,
                144.0,
                142.0,
            ],
            highs=[160.0] * 12,
            lows=[99.0] * 12,
            oi=[100.0, 140.0, 170.0, 180.0, 175.0, 165.0, 160.0, 155.0, 150.0, 148.0, 146.0, 144.0],
        )
    )
    assert r.triggered and r.side is SetupSide.SHORT


def test_s2_price_oi_divergence_short() -> None:
    r = detect_s2_price_oi_divergence(
        _ctx(
            closes=[100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 112.0],
            highs=[112.0] * 7,
            lows=[99.0] * 7,
            oi=[100.0, 99.0, 98.0, 97.0, 96.0, 95.0],
        )
    )
    assert r.triggered and r.side is SetupSide.SHORT


def test_registry_has_ten_detectors_all_callable() -> None:
    assert len(ALL_DETECTORS) == 10
    ctx = _ctx(closes=[1.0] * 30, highs=[1.0] * 30, lows=[1.0] * 30)
    for det in ALL_DETECTORS:
        res = det(ctx)
        assert res.name and isinstance(res.triggered, bool)
