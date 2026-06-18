"""Тесты бэктестера: TP/стоп exit, издержки, lookahead-independence, метрики."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from backtest.costs import CostModel
from backtest.engine import BacktestEngine, Trade
from backtest.metrics import compute_metrics
from backtest.strategy import Signal
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
    """Сигналит LONG один раз на свече с индексом at_index (0-based в history)."""

    def __init__(self, at_index: int, stop: Decimal, tp: Decimal) -> None:
        self._at = at_index
        self._stop = stop
        self._tp = tp
        self._fired = False

    def on_candle(self, history: Sequence[OHLCV]) -> Signal | None:
        if not self._fired and len(history) - 1 == self._at:
            self._fired = True
            return Signal(OrderSide.BUY, self._stop, self._tp, Decimal("0.005"))
        return None


def test_long_take_profit_with_costs() -> None:
    candles = [
        _c(0, "100", "100", "100", "100"),  # i0: сигнал
        _c(1, "100", "100.5", "99.5", "100"),  # i1: вход по open=100, без выхода
        _c(2, "101", "102.5", "101", "102"),  # i2: high≥102 → TP=102
        _c(3, "102", "102", "102", "102"),  # i3: запас (нужен c+1)
    ]
    eng = BacktestEngine(_OnceLong(0, Decimal("99"), Decimal("102")), COSTS, CFG, EQUITY0)
    res = eng.run(candles)
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.exit_reason == "tp"
    assert t.entry_price == Decimal("100")
    assert t.exit_price == Decimal("102")
    assert t.quantity == Decimal("50")  # 0.005*10000/0.01/100
    assert t.gross_pnl == Decimal("100")
    # издержки: вход 5000*0.001=5, выход 5100*0.001=5.1
    assert t.costs == Decimal("10.1")
    assert t.net_pnl == Decimal("89.9")
    assert res.equity_curve[-1] == Decimal("10089.9")


def test_long_stop_loss() -> None:
    candles = [
        _c(0, "100", "100", "100", "100"),
        _c(1, "100", "100.5", "99.5", "100"),
        _c(2, "100", "100", "98", "99"),  # low≤99 → стоп
        _c(3, "99", "99", "99", "99"),
    ]
    eng = BacktestEngine(_OnceLong(0, Decimal("99"), Decimal("110")), COSTS, CFG, EQUITY0)
    res = eng.run(candles)
    assert len(res.trades) == 1
    assert res.trades[0].exit_reason == "stop"
    assert res.trades[0].exit_price == Decimal("99")
    assert res.trades[0].gross_pnl == Decimal("-50")


def test_both_levels_in_bar_counts_as_stop() -> None:
    candles = [
        _c(0, "100", "100", "100", "100"),
        _c(1, "100", "100.5", "99.5", "100"),
        _c(2, "100", "111", "98", "105"),  # задеты и стоп(99), и тейк(110) → стоп
        _c(3, "105", "105", "105", "105"),
    ]
    eng = BacktestEngine(_OnceLong(0, Decimal("99"), Decimal("110")), COSTS, CFG, EQUITY0)
    res = eng.run(candles)
    assert res.trades[0].exit_reason == "stop"


def test_lookahead_independence_future_change_does_not_affect_closed_trade() -> None:
    base = [
        _c(0, "100", "100", "100", "100"),
        _c(1, "100", "100.5", "99.5", "100"),
        _c(2, "101", "102.5", "101", "102"),  # сделка закрывается здесь (TP)
        _c(3, "102", "102", "102", "102"),
    ]
    mutated = [*base[:3], _c(3, "200", "999", "1", "200")]  # будущая свеча искажена

    eng_a = BacktestEngine(_OnceLong(0, Decimal("99"), Decimal("102")), COSTS, CFG, EQUITY0)
    eng_b = BacktestEngine(_OnceLong(0, Decimal("99"), Decimal("102")), COSTS, CFG, EQUITY0)
    ta = eng_a.run(base).trades
    tb = eng_b.run(mutated).trades
    # сделка закрылась на i2 (< изменённой i3) → должна быть идентична
    assert ta == tb


def test_no_signal_no_trades() -> None:
    candles = [_c(i, "100", "101", "99", "100") for i in range(5)]
    eng = BacktestEngine(_OnceLong(99, Decimal("99"), Decimal("102")), COSTS, CFG, EQUITY0)
    res = eng.run(candles)
    assert res.trades == []
    assert res.equity_curve == [EQUITY0]


# ── метрики ──
def _trade(net: str) -> Trade:
    return Trade(
        entry_ts=0,
        exit_ts=1,
        side=OrderSide.BUY,
        entry_price=Decimal("100"),
        exit_price=Decimal("100"),
        quantity=Decimal("1"),
        gross_pnl=Decimal(net),
        costs=Decimal("0"),
        net_pnl=Decimal(net),
        exit_reason="tp",
    )


def test_metrics_basic() -> None:
    trades = [_trade("100"), _trade("-50")]
    curve = [Decimal("10000"), Decimal("10100"), Decimal("10050")]
    m = compute_metrics(trades, curve)
    assert m.num_trades == 2
    assert m.winrate == 0.5
    assert m.profit_factor == 2.0
    assert m.expectancy == Decimal("25")
    assert m.total_net_pnl == Decimal("50")
    assert m.max_drawdown_pct > 0


def test_metrics_no_losses_pf_none() -> None:
    m = compute_metrics([_trade("10"), _trade("20")], [Decimal("10000"), Decimal("10030")])
    assert m.profit_factor is None


def test_metrics_empty() -> None:
    m = compute_metrics([], [Decimal("10000")])
    assert m.num_trades == 0
    assert m.profit_factor is None
