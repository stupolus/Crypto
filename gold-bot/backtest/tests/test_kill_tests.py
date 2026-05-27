"""Тесты kill-tests модуля (coin-consistency, Bonferroni, overlap-corr, holdout)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backtest.kill_tests import (
    bonferroni_alpha,
    coin_consistency,
    evaluate_all,
    holdout_split,
    overlap_correlation,
    pf_threshold_under_bonferroni,
)

# ── Coin-consistency ──


def test_coin_consistency_pass_two_symbols_above_pf() -> None:
    r = coin_consistency({"A": Decimal("1.5"), "B": Decimal("1.2")})
    assert r.passed
    assert r.failing_symbols == ()


def test_coin_consistency_fail_one_symbol_below_pf() -> None:
    # B провален, остаётся только A — нужно ≥ 2 проходящих
    r = coin_consistency({"A": Decimal("1.5"), "B": Decimal("0.5")})
    assert not r.passed
    assert "B" in r.failing_symbols


def test_coin_consistency_treats_pf_none_as_fail() -> None:
    # PF = None трактуется как FAIL (бесконечные потери, нечего делить)
    r = coin_consistency({"A": Decimal("1.5"), "B": None})
    assert not r.passed
    assert "B" in r.failing_symbols


def test_coin_consistency_custom_pf_threshold() -> None:
    r = coin_consistency(
        {"A": Decimal("1.1"), "B": Decimal("1.1")},
        min_pf_per_symbol=Decimal("1.5"),
    )
    assert not r.passed  # обе ниже 1.5
    assert set(r.failing_symbols) == {"A", "B"}


def test_coin_consistency_empty() -> None:
    r = coin_consistency({})
    assert not r.passed


# ── Bonferroni ──


def test_bonferroni_alpha_n1() -> None:
    assert bonferroni_alpha(1) == 0.05


def test_bonferroni_alpha_n10() -> None:
    assert bonferroni_alpha(10) == 0.005


def test_bonferroni_alpha_n24() -> None:
    # ровно наш 24-grid сценарий
    assert abs(bonferroni_alpha(24) - 0.05 / 24) < 1e-9


def test_bonferroni_alpha_rejects_zero_or_negative() -> None:
    with pytest.raises(ValueError):
        bonferroni_alpha(0)
    with pytest.raises(ValueError):
        bonferroni_alpha(-1)


def test_pf_threshold_grows_with_n_tests() -> None:
    pf1 = pf_threshold_under_bonferroni(1)
    pf10 = pf_threshold_under_bonferroni(10)
    pf24 = pf_threshold_under_bonferroni(24)
    assert pf1 == Decimal("1.3")
    assert pf10 > pf1
    assert pf24 > pf10
    # 24 теста → 1.3 + 23*0.02 = 1.76
    assert pf24 == Decimal("1.76")


# ── Overlap correlation ──


def test_overlap_correlation_identical_streams() -> None:
    r = overlap_correlation(
        [Decimal("0.01"), Decimal("-0.02"), Decimal("0.03")] * 5,
        [Decimal("0.01"), Decimal("-0.02"), Decimal("0.03")] * 5,
    )
    assert r.correlation == Decimal("1.0000")
    assert r.high_correlation


def test_overlap_correlation_anticorrelated() -> None:
    r = overlap_correlation(
        [Decimal("0.01"), Decimal("-0.02"), Decimal("0.03")] * 5,
        [Decimal("-0.01"), Decimal("0.02"), Decimal("-0.03")] * 5,
    )
    assert r.correlation == Decimal("-1.0000")
    assert r.high_correlation  # abs(rho) >= 0.7


def test_overlap_correlation_uncorrelated() -> None:
    # ряды разной природы
    r = overlap_correlation(
        [Decimal(x) for x in ["0.01", "-0.02", "0.03", "-0.01", "0.02", "-0.03"]],
        [Decimal(x) for x in ["0.005", "0.01", "-0.005", "-0.01", "0.005", "0.01"]],
    )
    assert abs(r.correlation) < Decimal("0.5")
    assert not r.high_correlation


def test_overlap_correlation_short_streams() -> None:
    # < 2 элементов — возвращает 0
    r = overlap_correlation([Decimal("1")], [Decimal("1")])
    assert r.correlation == Decimal(0)
    assert not r.high_correlation


def test_overlap_correlation_zero_variance() -> None:
    # ряд с нулевой вариативностью → корреляция не определена, возвращаем 0
    r = overlap_correlation([Decimal("1")] * 10, [Decimal("1"), Decimal("2")] * 5)
    assert r.correlation == Decimal(0)


# ── Holdout split ──


def test_holdout_split_basic_20pct() -> None:
    s = holdout_split(10_000, holdout_fraction=0.2, min_holdout=1000)
    assert s.development_size == 8000
    assert s.holdout_size == 2000
    assert s.development_end_idx == 8000
    assert s.holdout_start_idx == 8000


def test_holdout_split_rejects_too_small_holdout() -> None:
    # 1000 свечей × 0.1 = 100 < min_holdout=500
    with pytest.raises(ValueError, match="holdout"):
        holdout_split(1000, holdout_fraction=0.1, min_holdout=500)


def test_holdout_split_rejects_invalid_fraction() -> None:
    with pytest.raises(ValueError):
        holdout_split(10_000, holdout_fraction=0.0)
    with pytest.raises(ValueError):
        holdout_split(10_000, holdout_fraction=1.0)


def test_holdout_split_rejects_zero_candles() -> None:
    with pytest.raises(ValueError):
        holdout_split(0)


# ── evaluate_all интеграция ──


def test_evaluate_all_passes_when_everything_clean() -> None:
    r = evaluate_all(
        per_symbol_pf={"BTC": Decimal("1.5"), "ETH": Decimal("1.4")},
        n_grid_tests=2,
        observed_pf_aggregate=Decimal("1.5"),
        holdout_pf=Decimal("1.2"),
    )
    assert r.coin_consistency_passed
    assert r.bonferroni_passed
    assert r.holdout_passed
    assert r.overall_passed
    assert r.rejection_reasons == ()


def test_evaluate_all_fails_on_bonferroni_with_many_tests() -> None:
    # 24 тестов → нужен PF ≥ 1.76, наблюдаем 1.4 → fail
    r = evaluate_all(
        per_symbol_pf={"BTC": Decimal("1.5"), "ETH": Decimal("1.4")},
        n_grid_tests=24,
        observed_pf_aggregate=Decimal("1.4"),
        holdout_pf=Decimal("1.2"),
    )
    assert not r.bonferroni_passed
    assert not r.overall_passed
    assert any("bonferroni" in reason for reason in r.rejection_reasons)


def test_evaluate_all_fails_on_l3_like_pattern() -> None:
    """Воспроизводим паттерн L3 Щукина: PF > 1.3 на BTC, провал на ETH."""
    r = evaluate_all(
        per_symbol_pf={"BTC": Decimal("1.5"), "ETH": Decimal("0.16")},  # ETH −84% эквив.
        n_grid_tests=10,
        observed_pf_aggregate=Decimal("1.3"),
        holdout_pf=Decimal("1.0"),
    )
    assert not r.coin_consistency_passed
    assert not r.overall_passed
    assert any("coin_consistency" in reason for reason in r.rejection_reasons)


def test_evaluate_all_handles_no_holdout() -> None:
    r = evaluate_all(
        per_symbol_pf={"BTC": Decimal("1.5"), "ETH": Decimal("1.4")},
        n_grid_tests=2,
        observed_pf_aggregate=Decimal("1.5"),
        holdout_pf=None,
    )
    assert not r.holdout_passed
    assert any("holdout_not_run" in reason for reason in r.rejection_reasons)


def test_evaluate_all_overlap_reduces_effective_n() -> None:
    """Если 2 ячейки сильно скоррелированы, effective_n уменьшается → проще пройти."""
    # При n=2 нужен PF ≥ 1.3 + 1*0.02 = 1.32
    # При overlap correction (high-corr пара) effective_n = 1 → PF ≥ 1.3
    r_no_corr = evaluate_all(
        per_symbol_pf={"A": Decimal("1.31"), "B": Decimal("1.31")},
        n_grid_tests=2,
        observed_pf_aggregate=Decimal("1.31"),
        holdout_pf=Decimal("1.1"),
        overlap_pairs=None,
    )
    r_with_corr = evaluate_all(
        per_symbol_pf={"A": Decimal("1.31"), "B": Decimal("1.31")},
        n_grid_tests=2,
        observed_pf_aggregate=Decimal("1.31"),
        holdout_pf=Decimal("1.1"),
        overlap_pairs={("A", "B"): Decimal("0.85")},
    )
    assert r_no_corr.overlap_corrected_tests == 2
    assert r_with_corr.overlap_corrected_tests == 1
    # без коррекции — fail (1.31 < 1.32), с коррекцией — pass (1.31 >= 1.30)
    assert not r_no_corr.bonferroni_passed
    assert r_with_corr.bonferroni_passed
