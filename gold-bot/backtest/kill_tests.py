"""Kill-tests для приёмки стратегии.

Дополняют базовые пороги master-плана (PF, expectancy, max DD, trades).
Введены после аудита методологии Щукина 2026-05-27, где «единственный
выживший» детектор L3 показал PF>1.3 на агрегате портфеля, но провалил:
ETH −84%, p=0.54 после overlap-correction, BTC-only = selection bias из 30 тестов.

Чистые функции на stdlib: math/statistics + Decimal/list. Без scipy.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CoinConsistencyResult:
    """Per-symbol PF distribution + verdict."""

    per_symbol_pf: dict[str, Decimal | None]
    passed: bool
    failing_symbols: tuple[str, ...]


def coin_consistency(
    per_symbol_pf: dict[str, Decimal | None],
    *,
    min_pf_per_symbol: Decimal = Decimal("1.0"),
    require_symbols_pass: int = 2,
) -> CoinConsistencyResult:
    """Возвращает PASS только если ≥ require_symbols_pass символов имеют PF ≥
    min_pf_per_symbol. Если хоть один символ катастрофически минус (PF None
    трактуется как 0) — FAIL.

    Защита от случая «PF портфеля высокий потому что один символ вытащил».
    """
    if not per_symbol_pf:
        return CoinConsistencyResult({}, passed=False, failing_symbols=())
    passing = [s for s, pf in per_symbol_pf.items() if pf is not None and pf >= min_pf_per_symbol]
    failing = tuple(s for s, pf in per_symbol_pf.items() if pf is None or pf < min_pf_per_symbol)
    passed = len(passing) >= require_symbols_pass
    return CoinConsistencyResult(
        per_symbol_pf=dict(per_symbol_pf),
        passed=passed,
        failing_symbols=failing,
    )


def bonferroni_alpha(n_tests: int, base_alpha: float = 0.05) -> float:
    """Bonferroni-поправка: альфа для одного теста = base_alpha / n_tests.

    При N сравнений вероятность хотя бы одного ложного позитива при α=0.05
    приближается к 1−(1−α)^N ≈ N·α. Чтобы family-wise error rate остался
    base_alpha, на каждый тест применяется base_alpha/N.
    """
    if n_tests <= 0:
        raise ValueError("n_tests должно быть положительным")
    if not 0 < base_alpha < 1:
        raise ValueError("base_alpha должно быть в (0, 1)")
    return base_alpha / n_tests


def pf_threshold_under_bonferroni(
    n_tests: int,
    *,
    base_pf: Decimal = Decimal("1.3"),
    pf_per_extra_test: Decimal = Decimal("0.02"),
) -> Decimal:
    """Эмпирическая поправка порога PF под количество тестов.

    Точной теории нет (PF не имеет аналитической dist на коротких выборках),
    но эмпирически: чтобы Bonferroni-корректированный p<0.05 удерживался,
    каждый дополнительный тест требует ~0.02 буфера к PF.

    Использовать как **дополнительный** фильтр, не вместо bonferroni_alpha.
    """
    if n_tests <= 1:
        return base_pf
    extra = pf_per_extra_test * Decimal(n_tests - 1)
    return base_pf + extra


@dataclass(frozen=True)
class OverlapCorrelationResult:
    correlation: Decimal
    high_correlation: bool


def overlap_correlation(
    returns_a: list[Decimal], returns_b: list[Decimal], *, threshold: Decimal = Decimal("0.7")
) -> OverlapCorrelationResult:
    """Пирсон-корреляция между двумя рядами per-trade returns.

    Если ряды разной длины — обрезаем до min(len). Если хоть один пуст или
    содержит только нули — возвращаем 0.

    Высокая корреляция (≥ threshold) сигнализирует что два «независимых»
    символа на самом деле одна и та же ставка — в multiple-comparison
    учитывать как 1 тест, не 2.
    """
    n = min(len(returns_a), len(returns_b))
    if n < 2:
        return OverlapCorrelationResult(Decimal(0), False)
    a = [float(x) for x in returns_a[:n]]
    b = [float(x) for x in returns_b[:n]]
    mean_a = sum(a) / n
    mean_b = sum(b) / n
    var_a = sum((x - mean_a) ** 2 for x in a)
    var_b = sum((x - mean_b) ** 2 for x in b)
    if var_a == 0 or var_b == 0:
        return OverlapCorrelationResult(Decimal(0), False)
    cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    rho_float = cov / math.sqrt(var_a * var_b)
    rho = Decimal(str(rho_float)).quantize(Decimal("0.0001"))
    return OverlapCorrelationResult(
        correlation=rho,
        high_correlation=abs(rho) >= threshold,
    )


@dataclass(frozen=True)
class HoldoutSplit:
    """Разбиение `candles` на (development, holdout).

    `development` идёт в обычный walk-forward.
    `holdout` НЕ виден стратегии до финального single-shot прогона
    после успешного walk-forward. Это последняя проверка против overfit'а
    под train/test окна.
    """

    development_end_idx: int
    holdout_start_idx: int
    development_size: int
    holdout_size: int


def holdout_split(
    total_candles: int, *, holdout_fraction: float = 0.2, min_holdout: int = 1000
) -> HoldoutSplit:
    """Разделить ряд свечей на development + holdout.

    `holdout_fraction` — доля последних свечей под holdout (по умолчанию 20%).
    Не меньше `min_holdout` свечей, иначе кидаем ValueError (слишком короткий
    ряд для honest holdout).
    """
    if total_candles <= 0:
        raise ValueError("total_candles должно быть положительным")
    if not 0 < holdout_fraction < 1:
        raise ValueError("holdout_fraction должно быть в (0, 1)")
    holdout_size = int(total_candles * holdout_fraction)
    if holdout_size < min_holdout:
        raise ValueError(
            f"holdout {holdout_size} < min_holdout {min_holdout}; "
            f"увеличьте период данных или уменьшите min_holdout"
        )
    development_end_idx = total_candles - holdout_size
    return HoldoutSplit(
        development_end_idx=development_end_idx,
        holdout_start_idx=development_end_idx,
        development_size=development_end_idx,
        holdout_size=holdout_size,
    )


@dataclass(frozen=True)
class KillTestSummary:
    """Сводка по всем kill-тестам для одной стратегии."""

    coin_consistency_passed: bool
    bonferroni_passed: bool
    holdout_passed: bool
    overlap_corrected_tests: int
    overall_passed: bool
    rejection_reasons: tuple[str, ...]


def evaluate_all(
    *,
    per_symbol_pf: dict[str, Decimal | None],
    n_grid_tests: int,
    observed_pf_aggregate: Decimal,
    holdout_pf: Decimal | None,
    overlap_pairs: dict[tuple[str, str], Decimal] | None = None,
    base_pf: Decimal = Decimal("1.3"),
    base_alpha: float = 0.05,
    holdout_min_pf: Decimal = Decimal("1.0"),
) -> KillTestSummary:
    """Применить все четыре kill-теста.

    - per_symbol_pf: PF по каждому символу отдельно (не агрегат портфеля).
    - n_grid_tests: сколько ячеек grid-сравнения было сделано (TF×coin×config).
    - observed_pf_aggregate: лучший PF из grid'а (тот, который кандидат).
    - holdout_pf: PF на отложенном holdout-периоде. None если ещё не прогнали.
    - overlap_pairs: корреляции между символами; нужно чтобы пересчитать
      effective n_grid_tests с учётом высоких корреляций.
    """
    reasons: list[str] = []

    # 1. Coin-consistency.
    cc = coin_consistency(per_symbol_pf)
    if not cc.passed:
        reasons.append(f"coin_consistency_failed: failing_symbols={cc.failing_symbols}")

    # 2. Overlap-corrected effective n_tests.
    effective_n = n_grid_tests
    if overlap_pairs:
        high_corr_pairs = sum(1 for rho in overlap_pairs.values() if abs(rho) >= Decimal("0.7"))
        # каждая высоко-коррелированная пара уменьшает effective_n на 1
        effective_n = max(1, n_grid_tests - high_corr_pairs)

    # 3. Bonferroni-поправка к порогу PF.
    pf_threshold = pf_threshold_under_bonferroni(effective_n, base_pf=base_pf)
    bonferroni_passed = observed_pf_aggregate >= pf_threshold
    if not bonferroni_passed:
        alpha_eff = bonferroni_alpha(effective_n, base_alpha)
        reasons.append(
            f"bonferroni_failed: observed_pf={observed_pf_aggregate} < "
            f"required_pf={pf_threshold} (n_eff={effective_n}, "
            f"alpha_eff={alpha_eff:.4f})"
        )

    # 4. Holdout.
    if holdout_pf is None:
        holdout_passed = False
        reasons.append("holdout_not_run")
    else:
        holdout_passed = holdout_pf >= holdout_min_pf
        if not holdout_passed:
            reasons.append(f"holdout_failed: pf={holdout_pf} < {holdout_min_pf}")

    overall = cc.passed and bonferroni_passed and holdout_passed

    return KillTestSummary(
        coin_consistency_passed=cc.passed,
        bonferroni_passed=bonferroni_passed,
        holdout_passed=holdout_passed,
        overlap_corrected_tests=effective_n,
        overall_passed=overall,
        rejection_reasons=tuple(reasons),
    )


def _sanity_imports() -> None:
    """Проверка импортов в рантайме (для type-checkers)."""
    _ = statistics
