"""Протокол стратегии для бэктеста и сигнал на вход.

Стратегия видит историю закрытых свечей `history[:i+1]` (включая текущую
закрытую), возвращает Signal на вход по open следующей свечи или None.
Будущее стратегия не видит — это гарантирует движок.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from exchanges.models import OHLCV, OrderSide


@dataclass(frozen=True)
class Signal:
    side: OrderSide
    stop: Decimal
    take_profit: Decimal
    risk_pct: Decimal
    asset_class: str = "crypto"


class Strategy(Protocol):
    def on_candle(self, history: Sequence[OHLCV]) -> Signal | None: ...
