"""Интрадей trend-following: пробой N-барного high (Donchian).

Long-only v1. Логика и обоснование параметров — `plans/10-strategy-donchian-breakout-2026-05-27.md`.

Контракт совместим с `backtest.Strategy`: видит `history[:i+1]` закрытых
свечей, возвращает `Signal` на вход по open следующей свечи (или None).
Lookahead-bias невозможен: канал Дончиана строится по `history[:-1]`
(прошедшие бары), пробой проверяется по close текущего бара.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from backtest.strategy import Signal
from exchanges.models import OHLCV, OrderSide
from indicators.core import atr, donchian
from strategies.donchian_breakout.config import StrategyParams

_MS_PER_HOUR = 3_600_000


class DonchianBreakout:
    """Long-only пробой N-барного экстремума с ATR-стопом и фикс. TP."""

    def __init__(self, params: StrategyParams, risk_pct: Decimal) -> None:
        self._p = params
        self._risk_pct = risk_pct
        # Состояние для cooldown: timestamp последней эмиссии сигнала.
        # Хранится в самой стратегии, потому что бэктест-движок не сообщает
        # стратегии о закрытии позиции. Cooldown по «последнему эмитированному
        # сигналу» — консервативно: даже если сайзинг отклонил сделку, окно
        # уважаем (значит edge момент был, не дёргаемся).
        self._last_signal_ts: int | None = None

    def _in_session(self, ts_ms: int) -> bool:
        hour = (ts_ms // _MS_PER_HOUR) % 24
        return self._p.session_start_hour_utc <= hour < self._p.session_end_hour_utc

    def on_candle(self, history: Sequence[OHLCV]) -> Signal | None:
        p = self._p
        # Минимум данных: канал из donchian_window предыдущих свечей +
        # текущая свеча-кандидат; и ATR требует period+1 свечу.
        if len(history) < max(p.donchian_window + 1, p.atr_period + 1):
            return None
        last = history[-1]
        if not self._in_session(last.timestamp):
            return None

        # Cooldown: bars_since_last_signal < cooldown_bars → пропуск.
        # Шаг таймфрейма выводим из последних двух свечей (не хардкодим).
        if self._last_signal_ts is not None and len(history) >= 2:
            tf_ms = history[-1].timestamp - history[-2].timestamp
            if tf_ms > 0:
                bars_since = (last.timestamp - self._last_signal_ts) // tf_ms
                if bars_since < p.cooldown_bars:
                    return None

        atr_vals = atr(history, p.atr_period)
        if not atr_vals:
            return None
        a = atr_vals[-1]
        if a <= 0:
            return None

        # Канал Дончиана строится по ПРЕДЫДУЩИМ donchian_window свечам,
        # не включая текущую свечу-кандидат (иначе тривиально close ≤ upper).
        channel = donchian(history[:-1], p.donchian_window)
        if channel is None:
            return None
        upper, _lower = channel

        # Long-only пробой. Short-версия — отдельный sub-план если long
        # покажет edge (асимметрия: золото в bull-bias на тестовом периоде).
        if last.close > upper:
            entry = last.close  # ориентир; фактический fill = next.open (движок)
            stop = entry - p.k_stop * a
            take_profit = entry + p.k_tp * a
            self._last_signal_ts = last.timestamp
            return Signal(OrderSide.BUY, stop, take_profit, self._risk_pct, p.asset_class)
        return None
