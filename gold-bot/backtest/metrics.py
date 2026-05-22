"""Метрики бэктеста. Денежные величины — Decimal; коэффициенты — float.

PF/expectancy/max DD считаются на Decimal-PnL. Sharpe/Sortino — per-trade
(без аннуализации; на низкой частоте аннуализация вводит в заблуждение).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from backtest.engine import Trade


@dataclass(frozen=True)
class Metrics:
    num_trades: int
    winrate: float
    profit_factor: float | None  # None если не было убытков (бесконечный PF)
    expectancy: Decimal
    avg_trade_after_costs: Decimal
    total_net_pnl: Decimal
    max_drawdown_pct: float
    sharpe_per_trade: float
    sortino_per_trade: float
    ulcer_index: float


def _max_drawdown_pct(equity_curve: Sequence[Decimal]) -> float:
    peak = equity_curve[0]
    max_dd = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = float((eq - peak) / peak)
            max_dd = min(max_dd, dd)
    return abs(max_dd)


def _ulcer(equity_curve: Sequence[Decimal]) -> float:
    peak = equity_curve[0]
    sq_sum = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = float((eq - peak) / peak) * 100 if peak > 0 else 0.0
        sq_sum += dd * dd
    return math.sqrt(sq_sum / len(equity_curve))


def compute_metrics(trades: Sequence[Trade], equity_curve: Sequence[Decimal]) -> Metrics:
    n = len(trades)
    if n == 0:
        return Metrics(0, 0.0, None, Decimal(0), Decimal(0), Decimal(0), 0.0, 0.0, 0.0, 0.0)

    nets = [t.net_pnl for t in trades]
    wins = [p for p in nets if p > 0]
    losses = [p for p in nets if p < 0]
    gross_profit = sum(wins, Decimal(0))
    gross_loss = -sum(losses, Decimal(0))
    pf = float(gross_profit / gross_loss) if gross_loss > 0 else None
    total = sum(nets, Decimal(0))
    expectancy = total / Decimal(n)

    fnets = [float(p) for p in nets]
    mean = sum(fnets) / n
    var = sum((x - mean) ** 2 for x in fnets) / n
    std = math.sqrt(var)
    sharpe = mean / std if std > 0 else 0.0
    downside = [x for x in fnets if x < 0]
    dvar = sum(x * x for x in downside) / n if downside else 0.0
    dstd = math.sqrt(dvar)
    sortino = mean / dstd if dstd > 0 else 0.0

    return Metrics(
        num_trades=n,
        winrate=len(wins) / n,
        profit_factor=pf,
        expectancy=expectancy,
        avg_trade_after_costs=expectancy,
        total_net_pnl=total,
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        sharpe_per_trade=sharpe,
        sortino_per_trade=sortino,
        ulcer_index=_ulcer(equity_curve),
    )
