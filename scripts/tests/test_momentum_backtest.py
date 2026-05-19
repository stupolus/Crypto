"""Тесты чистой логики momentum-бэктеста (без сети)."""

from __future__ import annotations

from scripts.momentum_backtest import (
    _parse_adjclose,
    momentum_score,
    select_top,
    simulate,
    walk_forward_split,
)

_DAY = 86_400_000


def test_momentum_score_basic() -> None:
    # 10 баров, lookback=3, skip=1: recent=closes[-2], past=closes[-5].
    closes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10.0]
    s = momentum_score(closes, lookback=3, skip=1)
    assert s == 9.0 / 6.0 - 1.0


def test_momentum_score_insufficient_history() -> None:
    assert momentum_score([1.0, 2.0], lookback=5, skip=1) is None


def test_momentum_score_guards_nonpositive_past() -> None:
    # past = closes[-1-skip-lookback] = closes[-4] = 0.0 → None.
    assert momentum_score([0.0, 1.0, 2.0, 3.0], lookback=3, skip=0) is None


def test_select_top_orders_and_truncates() -> None:
    scores = {"A": 0.1, "B": 0.5, "C": -0.2, "D": 0.5}
    # B и D равны → tie-break по имени (B перед D).
    assert select_top(scores, 2) == ["B", "D"]
    assert select_top(scores, 1) == ["B"]


def test_simulate_equal_weight_return() -> None:
    # Два символа, один растёт, держим оба после первого ребаланса.
    base = 1_000_000_000
    a = [(base + i * _DAY, 100.0 + i) for i in range(300)]
    b = [(base + i * _DAY, 100.0) for i in range(300)]
    curve = simulate({"A": a, "B": b}, k=2, lookback=20, skip=1, rebal=21, cost_pct=0.0)
    assert len(curve) == 300
    # Портфель должен вырасти (A растёт, B плоский) → equity > 1.
    assert curve[-1][1] > 1.0


def test_walk_forward_split_windows() -> None:
    base = 1_000_000_000
    curve = [(base + i * _DAY, 1.0 + i * 0.001) for i in range(900)]
    wins = walk_forward_split(curve, is_days=200, oos_days=100, step_days=100)
    assert len(wins) >= 3
    for w in wins:
        assert set(w) == {"pnl_pct", "pf", "sharpe", "max_dd_pct"}
        assert w["pnl_pct"] > 0  # монотонный рост


def test_parse_adjclose_skips_nulls() -> None:
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [100, 200, 300],
                    "indicators": {"adjclose": [{"adjclose": [10.0, None, 12.0]}]},
                }
            ]
        }
    }
    rows = _parse_adjclose(payload)
    assert rows == [(100_000, 10.0), (300_000, 12.0)]
