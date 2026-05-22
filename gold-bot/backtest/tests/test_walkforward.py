"""Тесты walk-forward: нарезка окон + агрегация OOS по нескольким окнам."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

import pytest

from backtest.costs import CostModel
from backtest.engine import BacktestEngine
from backtest.strategy import Signal
from backtest.walkforward import make_windows, run_walk_forward
from exchanges.models import OHLCV, OrderSide
from risk.config import load_risk_config

CFG = load_risk_config()
COSTS = CostModel(taker_fee=Decimal("0.0005"), slippage_pct=Decimal("0.0005"))
EQUITY0 = Decimal("10000")


def _c(ts: int, o: str, h: str, low: str, c: str) -> OHLCV:
    return OHLCV(
        timestamp=ts,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("1000"),
    )


class _OnceLong:
    def __init__(self) -> None:
        self._fired = False

    def on_candle(self, history: Sequence[OHLCV]) -> Signal | None:
        if not self._fired and len(history) == 1:
            self._fired = True
            return Signal(OrderSide.BUY, Decimal("99"), Decimal("102"), Decimal("0.005"))
        return None


def test_make_windows_anchored_rolling() -> None:
    windows = make_windows(12, train_size=2, test_size=4)
    assert len(windows) == 2
    assert (windows[0].is_start, windows[0].is_end) == (0, 2)
    assert (windows[0].oos_start, windows[0].oos_end) == (2, 6)
    assert (windows[1].oos_start, windows[1].oos_end) == (6, 10)


def test_make_windows_invalid() -> None:
    with pytest.raises(ValueError):
        make_windows(10, 0, 4)


def _entry_pattern(base_ts: int) -> list[OHLCV]:
    # 4 свечи: сигнал → вход → TP → запас
    return [
        _c(base_ts, "100", "100", "100", "100"),
        _c(base_ts + 1, "100", "100.5", "99.5", "100"),
        _c(base_ts + 2, "101", "102.5", "101", "102"),
        _c(base_ts + 3, "102", "102", "102", "102"),
    ]


def test_run_walk_forward_aggregates_two_windows() -> None:
    # 12 свечей: OOS-окна [2,6) и [6,10) — в каждом паттерн «вход→TP»
    candles = [_c(0, "100", "100", "100", "100"), _c(1, "100", "100", "100", "100")]
    candles += _entry_pattern(2)  # индексы 2..5
    candles += _entry_pattern(6)  # индексы 6..9
    candles += [_c(10, "100", "100", "100", "100"), _c(11, "100", "100", "100", "100")]

    report = run_walk_forward(
        candles,
        lambda _is: BacktestEngine(_OnceLong(), COSTS, CFG, EQUITY0),
        train_size=2,
        test_size=4,
        equity0=EQUITY0,
    )
    assert len(report.windows) == 2
    assert all(w.metrics.num_trades == 1 for w in report.windows)
    assert report.oos_aggregate.num_trades == 2
    assert all(t.exit_reason == "tp" for wr in report.windows for t in wr.trades)
