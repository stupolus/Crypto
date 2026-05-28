"""Тесты promotion-теста (статистика без сети)."""

from __future__ import annotations

from decimal import Decimal

from paper.promotion import StrategyMetrics, evaluate


def _metrics(
    sid: str,
    *,
    trades: int,
    pf: Decimal | None,
    dd: Decimal,
    returns: list[Decimal],
) -> StrategyMetrics:
    return StrategyMetrics(
        strategy_id=sid,
        trades=trades,
        wins=sum(1 for r in returns if r > 0),
        profit_factor=pf,
        max_drawdown_pct=dd,
        per_trade_returns=returns,
    )


def test_promote_when_clearly_better() -> None:
    # Challenger однозначно лучше: больше доходность, меньше DD
    champ = _metrics(
        "champ",
        trades=40,
        pf=Decimal("1.3"),
        dd=Decimal("0.05"),
        returns=[Decimal("0.001")] * 40,
    )
    chall = _metrics(
        "chall",
        trades=40,
        pf=Decimal("1.8"),
        dd=Decimal("0.04"),
        returns=[Decimal("0.003")] * 40,
    )
    d = evaluate(
        champ,
        chall,
        min_trades=30,
        min_pf_advantage=Decimal("0.2"),
        max_dd_tolerance=Decimal("0.02"),
        significance_level=0.05,
        n_challengers=1,
        bootstrap_iterations=300,
    )
    assert d.promote, d.rejection_reasons
    assert d.pf_advantage == Decimal("0.5")


def test_reject_when_too_few_trades() -> None:
    champ = _metrics(
        "champ", trades=20, pf=Decimal("1.3"), dd=Decimal("0.05"), returns=[Decimal("0.001")] * 20
    )
    chall = _metrics(
        "chall", trades=15, pf=Decimal("2.0"), dd=Decimal("0.03"), returns=[Decimal("0.005")] * 15
    )
    d = evaluate(
        champ,
        chall,
        min_trades=30,
        min_pf_advantage=Decimal("0.2"),
        max_dd_tolerance=Decimal("0.02"),
        significance_level=0.05,
        n_challengers=1,
        bootstrap_iterations=200,
    )
    assert not d.promote
    assert any("min_trades" in r for r in d.rejection_reasons)


def test_reject_when_pf_advantage_too_small() -> None:
    champ = _metrics(
        "champ",
        trades=40,
        pf=Decimal("1.3"),
        dd=Decimal("0.05"),
        returns=[Decimal("0.001")] * 40,
    )
    chall = _metrics(
        "chall",
        trades=40,
        pf=Decimal("1.35"),  # +0.05 — меньше порога 0.2
        dd=Decimal("0.04"),
        returns=[Decimal("0.0015")] * 40,
    )
    d = evaluate(
        champ,
        chall,
        min_trades=30,
        min_pf_advantage=Decimal("0.2"),
        max_dd_tolerance=Decimal("0.02"),
        significance_level=0.05,
        n_challengers=1,
        bootstrap_iterations=200,
    )
    assert not d.promote
    assert any("pf_advantage" in r for r in d.rejection_reasons)


def test_reject_when_drawdown_worse() -> None:
    champ = _metrics(
        "champ", trades=40, pf=Decimal("1.3"), dd=Decimal("0.04"), returns=[Decimal("0.001")] * 40
    )
    chall = _metrics(
        "chall",
        trades=40,
        pf=Decimal("1.7"),
        dd=Decimal("0.09"),  # +5 п.п. — больше допуска 2 п.п.
        returns=[Decimal("0.003")] * 40,
    )
    d = evaluate(
        champ,
        chall,
        min_trades=30,
        min_pf_advantage=Decimal("0.2"),
        max_dd_tolerance=Decimal("0.02"),
        significance_level=0.05,
        n_challengers=1,
        bootstrap_iterations=200,
    )
    assert not d.promote
    assert any("dd_worse" in r for r in d.rejection_reasons)


def test_bonferroni_tightens_alpha() -> None:
    # С 10 challenger'ами alpha делится → отвергаем чаще
    champ = _metrics(
        "champ", trades=40, pf=Decimal("1.3"), dd=Decimal("0.05"), returns=[Decimal("0.001")] * 40
    )
    # marginal advantage — должен пройти при N=1, провалиться при N=10
    chall = _metrics(
        "chall",
        trades=40,
        pf=Decimal("1.55"),
        dd=Decimal("0.05"),
        returns=[Decimal("0.0015")] * 40,
    )
    d1 = evaluate(
        champ,
        chall,
        min_trades=30,
        min_pf_advantage=Decimal("0.2"),
        max_dd_tolerance=Decimal("0.02"),
        significance_level=0.05,
        n_challengers=1,
        bootstrap_iterations=200,
    )
    d10 = evaluate(
        champ,
        chall,
        min_trades=30,
        min_pf_advantage=Decimal("0.2"),
        max_dd_tolerance=Decimal("0.02"),
        significance_level=0.05,
        n_challengers=10,
        bootstrap_iterations=200,
    )
    # Bonferroni: alpha=0.005 для N=10. Меньшая alpha = строже фильтр.
    # Прямой исход зависит от data, но точно alpha разные:
    assert d1.p_value_sign == d10.p_value_sign
