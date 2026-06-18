"""Тесты сигнала mean-reversion VWAP (синтетика, без сети)."""

from __future__ import annotations

from decimal import Decimal

from exchanges.models import OHLCV, OrderSide
from indicators.core import atr, vwap
from strategies.mean_reversion_vwap.config import StrategyParams, load_params
from strategies.mean_reversion_vwap.strategy import MeanReversionVWAP

RISK = Decimal("0.005")


def _p(**ov: object) -> StrategyParams:
    base: dict[str, object] = {
        "vwap_window": 3,
        "atr_period": 2,
        "k_entry": Decimal("1"),
        "k_stop": Decimal("1"),
        "session_start_hour_utc": 0,
        "session_end_hour_utc": 24,
        "asset_class": "metals",
    }
    base.update(ov)
    return StrategyParams.model_validate(base)


def _c(i: int, o: str, h: str, low: str, c: str) -> OHLCV:
    return OHLCV(
        timestamp=i * 900_000,  # 15m шаг, попадает в час 0/1
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("1000"),
    )


def _flat(n: int) -> list[OHLCV]:
    return [_c(i, "100", "101", "99", "100") for i in range(n)]


def test_long_when_below_lower_band() -> None:
    hist = [*_flat(4), _c(4, "80", "81", "79", "80")]  # резкое отклонение вниз
    strat = MeanReversionVWAP(_p(), RISK)
    a = atr(hist, 2)[-1]
    vw = vwap(hist[-3:])
    assert vw is not None
    sig = strat.on_candle(hist)
    assert sig is not None
    assert sig.side is OrderSide.BUY
    assert sig.take_profit == vw
    assert sig.stop == Decimal("80") - Decimal("1") * a
    assert sig.risk_pct == RISK
    assert sig.asset_class == "metals"


def test_short_when_above_upper_band() -> None:
    hist = [*_flat(4), _c(4, "120", "121", "119", "120")]  # резкое отклонение вверх
    strat = MeanReversionVWAP(_p(), RISK)
    a = atr(hist, 2)[-1]
    vw = vwap(hist[-3:])
    assert vw is not None
    sig = strat.on_candle(hist)
    assert sig is not None
    assert sig.side is OrderSide.SELL
    assert sig.take_profit == vw
    assert sig.stop == Decimal("120") + Decimal("1") * a


def test_none_inside_band() -> None:
    hist = _flat(5)  # цена у VWAP, в полосе
    strat = MeanReversionVWAP(_p(), RISK)
    assert strat.on_candle(hist) is None


def test_none_out_of_session() -> None:
    hist = [*_flat(4), _c(4, "80", "81", "79", "80")]
    strat = MeanReversionVWAP(_p(session_start_hour_utc=8, session_end_hour_utc=9), RISK)
    assert strat.on_candle(hist) is None  # час 0 вне окна 8-9


def test_none_insufficient_data() -> None:
    strat = MeanReversionVWAP(_p(), RISK)
    assert strat.on_candle(_flat(2)) is None


def test_config_loads_real_params() -> None:
    p = load_params()
    assert p.vwap_window == 32
    assert p.session_start_hour_utc == 7
