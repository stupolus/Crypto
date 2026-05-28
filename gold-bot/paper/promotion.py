"""Promotion-тест: champion vs challenger по out-of-sample.

См. plan 08 §«PromotionDecision». Без scipy: используем стандартную
библиотеку (random для bootstrap, statistics) — это достаточно для
N сделок порядка сотен, и не тянет тяжёлую зависимость в production.

Решающие критерии (все обязаны выполниться):
1. У обоих участников ≥ `min_trades` закрытых сделок в окне.
2. Bootstrap-доверительный интервал на разность медианных per-trade
   returns не пересекает 0 (challenger лучше) на уровне 1−α.
3. Sign-test: доля сделок, где challenger >= champion по per-trade
   returns, статистически > 50% (Bonferroni-поправка по количеству
   challenger'ов).
4. Разница в PF (challenger − champion) ≥ `min_pf_advantage`.
5. Max DD challenger'а не хуже champion'а на > `max_dd_tolerance` п.п.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from paper.journal import PaperJournal, TradeRecord


@dataclass(frozen=True)
class StrategyMetrics:
    strategy_id: str
    trades: int
    wins: int
    profit_factor: Decimal | None
    max_drawdown_pct: Decimal
    per_trade_returns: list[Decimal]


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    challenger_id: str
    champion_id: str
    p_value_sign: float
    bootstrap_ci_low: Decimal
    bootstrap_ci_high: Decimal
    pf_advantage: Decimal | None
    dd_delta: Decimal
    rejection_reasons: tuple[str, ...]
    metrics_champion: StrategyMetrics
    metrics_challenger: StrategyMetrics


def _per_trade_returns(trades: list[TradeRecord], starting_equity: Decimal) -> list[Decimal]:
    """Возвращает PnL каждой сделки нормализованный на доступный капитал
    к моменту входа. Для простоты используется equity на начало журнала."""
    if starting_equity <= 0:
        return []
    return [t.net_pnl / starting_equity for t in trades]


def _max_drawdown_pct(trades: list[TradeRecord]) -> Decimal:
    if not trades:
        return Decimal(0)
    peak = trades[0].equity_after
    max_dd = Decimal(0)
    for t in trades:
        if t.equity_after > peak:
            peak = t.equity_after
        if peak > 0:
            dd = (peak - t.equity_after) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def _profit_factor(trades: list[TradeRecord]) -> Decimal | None:
    losses = sum((-t.net_pnl for t in trades if t.net_pnl < 0), Decimal(0))
    wins = sum((t.net_pnl for t in trades if t.net_pnl > 0), Decimal(0))
    if losses == 0:
        return None
    return wins / losses


def compute_metrics(
    journal: PaperJournal, strategy_id: str, starting_equity: Decimal
) -> StrategyMetrics:
    trades = journal.list_trades()
    wins = sum(1 for t in trades if t.net_pnl > 0)
    return StrategyMetrics(
        strategy_id=strategy_id,
        trades=len(trades),
        wins=wins,
        profit_factor=_profit_factor(trades),
        max_drawdown_pct=_max_drawdown_pct(trades),
        per_trade_returns=_per_trade_returns(trades, starting_equity),
    )


def _bootstrap_ci_diff(
    sample_challenger: list[Decimal],
    sample_champion: list[Decimal],
    *,
    iterations: int,
    alpha: float,
    seed: int,
) -> tuple[Decimal, Decimal]:
    """Перцентильный bootstrap-доверительный интервал на разность медиан."""
    rng = random.Random(seed)
    n_a = len(sample_challenger)
    n_b = len(sample_champion)
    if n_a == 0 or n_b == 0:
        return Decimal(0), Decimal(0)
    diffs: list[Decimal] = []
    for _ in range(iterations):
        a_resample = sorted(sample_challenger[rng.randrange(n_a)] for _ in range(n_a))
        b_resample = sorted(sample_champion[rng.randrange(n_b)] for _ in range(n_b))
        diffs.append(a_resample[n_a // 2] - b_resample[n_b // 2])
    diffs.sort()
    low_idx = int(iterations * (alpha / 2))
    high_idx = int(iterations * (1 - alpha / 2)) - 1
    high_idx = min(high_idx, iterations - 1)
    return diffs[low_idx], diffs[high_idx]


def _binom_pvalue_two_sided(k: int, n: int) -> float:
    """P(|X − n/2| ≥ |k − n/2|), X ~ Binom(n, 0.5)."""
    if n == 0:
        return 1.0
    mean = n / 2
    target = abs(k - mean)
    p = 0.0
    for i in range(n + 1):
        if abs(i - mean) >= target:
            p += float(math.comb(n, i))
    return p / float(2**n)


def _sign_test_pvalue(returns_challenger: list[Decimal], returns_champion: list[Decimal]) -> float:
    """Sign-test на парных сравнениях. Если выборки разной длины, обрезаем
    до min(len). Чёткой парности по времени мы не имеем (paper-движки могут
    стартовать сигнал в разные свечи), поэтому считаем по отсортированным
    рядам — это даёт оценку «в среднем challenger чаще лучше champion»."""
    n = min(len(returns_challenger), len(returns_champion))
    if n == 0:
        return 1.0
    a = sorted(returns_challenger, reverse=True)[:n]
    b = sorted(returns_champion, reverse=True)[:n]
    wins = sum(1 for i in range(n) if a[i] > b[i])
    return _binom_pvalue_two_sided(wins, n)


def evaluate(
    champion: StrategyMetrics,
    challenger: StrategyMetrics,
    *,
    min_trades: int,
    min_pf_advantage: Decimal,
    max_dd_tolerance: Decimal,
    significance_level: float,
    n_challengers: int,
    bootstrap_iterations: int = 1000,
    seed: int = 0xC0DE,
) -> PromotionDecision:
    """Полный promotion-тест по правилам plan 08."""
    reasons: list[str] = []

    if champion.trades < min_trades:
        reasons.append(f"champion_min_trades<{min_trades}")
    if challenger.trades < min_trades:
        reasons.append(f"challenger_min_trades<{min_trades}")

    alpha = significance_level / max(1, n_challengers)  # Bonferroni
    p_sign = _sign_test_pvalue(challenger.per_trade_returns, champion.per_trade_returns)
    if p_sign >= alpha:
        reasons.append(f"sign_test_not_significant p={p_sign:.4f} alpha={alpha:.4f}")

    ci_low, ci_high = _bootstrap_ci_diff(
        challenger.per_trade_returns,
        champion.per_trade_returns,
        iterations=bootstrap_iterations,
        alpha=alpha,
        seed=seed,
    )
    if ci_low <= 0:
        reasons.append(f"bootstrap_ci_includes_zero low={ci_low} high={ci_high}")

    pf_adv: Decimal | None
    if champion.profit_factor is None or challenger.profit_factor is None:
        pf_adv = None
        if challenger.profit_factor is None:
            reasons.append("challenger_pf_none")
    else:
        pf_adv = challenger.profit_factor - champion.profit_factor
        if pf_adv < min_pf_advantage:
            reasons.append(f"pf_advantage<{min_pf_advantage}")

    dd_delta = challenger.max_drawdown_pct - champion.max_drawdown_pct
    if dd_delta > max_dd_tolerance:
        reasons.append(f"dd_worse_by={dd_delta}")

    return PromotionDecision(
        promote=not reasons,
        challenger_id=challenger.strategy_id,
        champion_id=champion.strategy_id,
        p_value_sign=p_sign,
        bootstrap_ci_low=ci_low,
        bootstrap_ci_high=ci_high,
        pf_advantage=pf_adv,
        dd_delta=dd_delta,
        rejection_reasons=tuple(reasons),
        metrics_champion=champion,
        metrics_challenger=challenger,
    )


def _trades_in_window(journal: PaperJournal, start_day: date, end_day: date) -> list[TradeRecord]:
    """Сделки с exit_ts в [start_day, end_day) UTC."""
    out: list[TradeRecord] = []
    cur = start_day
    from datetime import timedelta

    while cur < end_day:
        out.extend(journal.list_trades(cur))
        cur += timedelta(days=1)
    return out
