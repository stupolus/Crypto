"""Стоимостная модель: комиссии + слиппедж на каждую ногу сделки.

Издержки считаются на вход и выход (round-trip) как доля notional ноги.
funding для интрадей-перпов мал на горизонте сделки, но учитывается
отдельно в paper/live.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CostModel:
    taker_fee: Decimal  # доля notional, напр. 0.0005
    slippage_pct: Decimal  # доля цены, напр. 0.0005

    def leg_cost(self, notional: Decimal) -> Decimal:
        """Издержки одной ноги (вход или выход) от её notional."""
        return notional * (self.taker_fee + self.slippage_pct)
