"""Тесты изолированного бэктест-харнеса DOLF (план 23 фаза 23.2)."""

from __future__ import annotations

from decimal import Decimal

from core.signals.composite import (
    StaticDeltaProvider,
    StaticFundingProvider,
    StaticLiquidationProvider,
    StaticOpenInterestProvider,
)
from core.signals.dolf_backtest import Candle, evaluate_detector
from core.signals.dolf_setups import DolfContext, SetupResult, SetupSide

_SYM = "BTC-USDT"


def _uptrend(n: int) -> list[Candle]:
    out: list[Candle] = []
    price = Decimal("100")
    for i in range(n):
        price *= Decimal("1.01")
        out.append(
            Candle(
                open_time_ms=i * 4 * 3_600_000,
                high=price * Decimal("1.001"),
                low=price * Decimal("0.999"),
                close=price,
                volume=Decimal("1000"),
            )
        )
    return out


def _always(side: SetupSide) -> object:
    def det(ctx: DolfContext) -> SetupResult:
        return SetupResult(True, "fake", side, "always")

    return det


def _never(ctx: DolfContext) -> SetupResult:
    return SetupResult(False, "fake")


def _providers() -> dict[str, object]:
    return {
        "liq": StaticLiquidationProvider(),
        "oi": StaticOpenInterestProvider(),
        "delta": StaticDeltaProvider(),
        "funding": StaticFundingProvider({_SYM: None}),
    }


def test_long_detector_on_uptrend_all_wins() -> None:
    candles = _uptrend(60)
    p = _providers()
    st = evaluate_detector(
        _always(SetupSide.LONG),  # type: ignore[arg-type]
        candles,
        liq=p["liq"],  # type: ignore[arg-type]
        oi=p["oi"],  # type: ignore[arg-type]
        delta=p["delta"],  # type: ignore[arg-type]
        funding=p["funding"],  # type: ignore[arg-type]
        symbol=_SYM,
        horizon_bars=6,
        min_history=5,
    )
    assert st.trades == 60 - 6 - 5
    assert st.win_rate == 100.0
    assert st.avg_return_pct > 0
    assert st.profit_factor == float("inf")


def test_short_detector_on_uptrend_all_losses() -> None:
    candles = _uptrend(40)
    p = _providers()
    st = evaluate_detector(
        _always(SetupSide.SHORT),  # type: ignore[arg-type]
        candles,
        liq=p["liq"],  # type: ignore[arg-type]
        oi=p["oi"],  # type: ignore[arg-type]
        delta=p["delta"],  # type: ignore[arg-type]
        funding=p["funding"],  # type: ignore[arg-type]
        symbol=_SYM,
        horizon_bars=6,
        min_history=5,
    )
    assert st.trades == 40 - 6 - 5
    assert st.win_rate == 0.0
    assert st.profit_factor == 0.0
    assert not st.passes


def test_never_trigger_yields_zero_and_not_passes() -> None:
    st = evaluate_detector(
        _never,
        _uptrend(50),
        liq=StaticLiquidationProvider(),
        oi=StaticOpenInterestProvider(),
        delta=StaticDeltaProvider(),
        funding=StaticFundingProvider({_SYM: None}),
        symbol=_SYM,
    )
    assert st.trades == 0
    assert not st.passes


def test_passes_criterion_logic() -> None:
    from core.signals.dolf_backtest import DetectorStats

    good = DetectorStats(
        "x", trades=40, win_rate=60, profit_factor=1.5, sharpe=1.2, avg_return_pct=0.5
    )
    assert good.passes
    thin = DetectorStats(
        "x", trades=10, win_rate=80, profit_factor=2.0, sharpe=3.0, avg_return_pct=1.0
    )
    assert not thin.passes
    weak_pf = DetectorStats(
        "x", trades=50, win_rate=55, profit_factor=1.1, sharpe=1.5, avg_return_pct=0.2
    )
    assert not weak_pf.passes
