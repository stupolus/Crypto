"""Расчёт сводных метрик backtest'а."""

from __future__ import annotations

import math
from collections.abc import Sequence
from decimal import Decimal

from core.backtest.models import BacktestSummary, Trade

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


def _decimal_sqrt(value: Decimal) -> Decimal:
    """Decimal sqrt через float — для Sharpe-аннуализации."""
    if value <= 0:
        return _ZERO
    return Decimal(str(math.sqrt(float(value))))


def compute_summary(
    trades: Sequence[Trade],
    equity_curve: Sequence[tuple[int, Decimal]],
    initial_equity: Decimal,
    minutes_per_period: int = 60 * 24,
) -> BacktestSummary:
    """Свести trades + equity_curve в summary.

    ``minutes_per_period`` нужен для аннуализации Sharpe — сколько торговых
    минут в «году». Для крипты, торгуемой 24/7, год = 365 × 24 × 60 минут.
    """
    if not trades:
        return BacktestSummary(
            total_trades=0,
            win_rate=_ZERO,
            avg_win_pct=_ZERO,
            avg_loss_pct=_ZERO,
            profit_factor=_ZERO,
            sharpe_ratio=_ZERO,
            max_drawdown_pct=_ZERO,
            final_equity=initial_equity,
            total_pnl_pct=_ZERO,
            avg_trade_duration_minutes=_ZERO,
        )

    wins = [t for t in trades if t.is_win]
    losses = [t for t in trades if t.is_loss]
    total = Decimal(len(trades))
    win_rate = (Decimal(len(wins)) / total) * _HUNDRED

    avg_win_pct = (
        sum((t.pnl_pct for t in wins), _ZERO) / Decimal(len(wins))
        if wins
        else _ZERO
    )
    avg_loss_pct = (
        sum((t.pnl_pct for t in losses), _ZERO) / Decimal(len(losses))
        if losses
        else _ZERO
    )
    gross_win = sum((t.pnl for t in wins), _ZERO)
    gross_loss_abs = -sum((t.pnl for t in losses), _ZERO)
    profit_factor = (
        gross_win / gross_loss_abs if gross_loss_abs > 0 else _ZERO
    )

    # Sharpe: returns per trade (pnl_pct в долях).
    returns = [t.pnl_pct / _HUNDRED for t in trades]
    mean = sum(returns, _ZERO) / total
    variance = sum(((r - mean) ** 2 for r in returns), _ZERO) / total
    stdev = _decimal_sqrt(variance)
    if stdev == 0:
        sharpe = _ZERO
    else:
        # Аннуализация: предполагаем равномерное распределение сделок по
        # времени. avg_trade_minutes на сделку → N сделок в год.
        avg_duration_min = sum(
            (Decimal(t.duration_ms) / Decimal(60_000) for t in trades), _ZERO
        ) / total
        # Минимум 1 минута, чтобы не делить на 0.
        avg_duration_min = max(avg_duration_min, Decimal("1"))
        trades_per_year = Decimal(365 * 24 * 60) / avg_duration_min
        sharpe = (mean / stdev) * _decimal_sqrt(trades_per_year)
    avg_duration_min = sum(
        (Decimal(t.duration_ms) / Decimal(60_000) for t in trades), _ZERO
    ) / total

    # Max drawdown по equity_curve.
    max_dd = _ZERO
    peak = initial_equity
    for _, equity in equity_curve:
        if equity > peak:
            peak = equity
        if peak > 0:
            dd = (peak - equity) / peak * _HUNDRED
            if dd > max_dd:
                max_dd = dd

    final_equity = equity_curve[-1][1] if equity_curve else initial_equity
    total_pnl_pct = (
        (final_equity - initial_equity) / initial_equity * _HUNDRED
        if initial_equity > 0
        else _ZERO
    )

    return BacktestSummary(
        total_trades=len(trades),
        win_rate=win_rate.quantize(Decimal("0.01")),
        avg_win_pct=avg_win_pct.quantize(Decimal("0.0001")),
        avg_loss_pct=avg_loss_pct.quantize(Decimal("0.0001")),
        profit_factor=profit_factor.quantize(Decimal("0.0001")),
        sharpe_ratio=sharpe.quantize(Decimal("0.0001")),
        max_drawdown_pct=max_dd.quantize(Decimal("0.0001")),
        final_equity=final_equity.quantize(Decimal("0.00000001")),
        total_pnl_pct=total_pnl_pct.quantize(Decimal("0.0001")),
        avg_trade_duration_minutes=avg_duration_min.quantize(Decimal("0.01")),
    )
