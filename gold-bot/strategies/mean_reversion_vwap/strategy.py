"""Интрадей mean-reversion у VWAP±ATR (реализует backtest.Strategy).

Long при close < VWAP − k_entry·ATR (стоп = close − k_stop·ATR, TP = VWAP);
Short зеркально. Только в боевом сессионном окне. Размер позиции считает
RiskEngine; risk_pct инжектится при создании (из risk-profile), не хардкод.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from backtest.strategy import Signal
from exchanges.models import OHLCV, OrderSide
from indicators.core import atr, vwap
from strategies.mean_reversion_vwap.config import StrategyParams

_MS_PER_HOUR = 3_600_000


class MeanReversionVWAP:
    def __init__(self, params: StrategyParams, risk_pct: Decimal) -> None:
        self._p = params
        self._risk_pct = risk_pct

    def _in_session(self, ts_ms: int) -> bool:
        hour = (ts_ms // _MS_PER_HOUR) % 24
        return self._p.session_start_hour_utc <= hour < self._p.session_end_hour_utc

    def on_candle(self, history: Sequence[OHLCV]) -> Signal | None:
        p = self._p
        if len(history) < max(p.vwap_window, p.atr_period + 1):
            return None
        last = history[-1]
        if not self._in_session(last.timestamp):
            return None

        atr_vals = atr(history, p.atr_period)
        if not atr_vals:
            return None
        a = atr_vals[-1]
        if a <= 0:
            return None
        vw = vwap(history[-p.vwap_window :])
        if vw is None:
            return None

        close = last.close
        band = p.k_entry * a
        if close < vw - band:
            return Signal(OrderSide.BUY, close - p.k_stop * a, vw, self._risk_pct, p.asset_class)
        if close > vw + band:
            return Signal(OrderSide.SELL, close + p.k_stop * a, vw, self._risk_pct, p.asset_class)
        return None
