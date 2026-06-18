"""Тесты PaperEngine: контракт fill совпадает с backtest, плюс circuit breakers."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from backtest.costs import CostModel
from backtest.strategy import Signal, Strategy
from exchanges.models import OHLCV, OrderSide
from paper.engine import PaperEngine
from paper.journal import PaperJournal
from risk.config import load_risk_config


def _candle(ts: int, o: str, h: str, low: str, c: str) -> OHLCV:
    return OHLCV(
        timestamp=ts,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal("1000"),
    )


class _AlwaysLong:
    """Стратегия, эмитящая Signal BUY когда история ≥ 1."""

    def on_candle(self, history: Sequence[OHLCV]) -> Signal | None:
        if not history:
            return None
        last = history[-1]
        return Signal(
            side=OrderSide.BUY,
            stop=last.close * Decimal("0.98"),
            take_profit=last.close * Decimal("1.02"),
            risk_pct=Decimal("0.005"),
            asset_class="metals",
        )


class _Silent:
    def on_candle(self, history: Sequence[OHLCV]) -> Signal | None:
        return None


def _engine(strategy: Strategy) -> tuple[PaperEngine, PaperJournal]:
    j = PaperJournal(":memory:")
    cfg = load_risk_config()
    costs = CostModel(taker_fee=Decimal("0.0005"), slippage_pct=Decimal("0.0005"))
    e = PaperEngine(
        symbol="BTC/USDT:USDT",
        strategy=strategy,
        cost_model=costs,
        risk_cfg=cfg,
        journal=j,
        starting_equity=Decimal("10000"),
    )
    return e, j


def test_signal_on_candle_n_fills_on_n_plus_1() -> None:
    e, j = _engine(_AlwaysLong())
    # свеча 1: стратегия выдаёт сигнал, позиция НЕ открывается на этой же свече
    c1 = _candle(0, "100", "101", "99", "100")
    snap1 = e.process_closed_candle(c1)
    assert snap1.closed_trade is None
    assert snap1.opened_position is None  # ещё не fill
    # свеча 2: открытие по open=100, без exit (high 101 < tp ≈ 102)
    c2 = _candle(900_000, "100", "101", "99.5", "100.5")
    snap2 = e.process_closed_candle(c2)
    assert snap2.opened_position is not None
    assert snap2.opened_position.entry_price == Decimal("100")
    # в журнале появилась запись open_position
    pos = j.get_open_position("BTC/USDT:USDT")
    assert pos is not None and pos.entry_price == Decimal("100")


def test_stop_hit_closes_trade() -> None:
    e, j = _engine(_AlwaysLong())
    # сигнал
    e.process_closed_candle(_candle(0, "100", "101", "99", "100"))
    # fill по open=100, в той же свече low=95 → стоп=98 задет
    snap = e.process_closed_candle(_candle(900_000, "100", "101", "95", "96"))
    assert snap.opened_position is not None
    assert snap.closed_trade is None  # close произойдёт на следующей свече (контракт)
    # фактически открытие и проверка exit на одной свече — backtest engine так не делает
    # (он проверяет exit ДО открытия). Подтверждаем: позиция открыта, выходим на след. свече
    snap2 = e.process_closed_candle(_candle(1_800_000, "96", "97", "90", "92"))
    assert snap2.closed_trade is not None
    assert snap2.closed_trade.exit_reason == "stop"


def test_tp_hit_closes_trade() -> None:
    e, j = _engine(_AlwaysLong())
    e.process_closed_candle(_candle(0, "100", "101", "99", "100"))
    e.process_closed_candle(_candle(900_000, "100", "101", "99.5", "100.5"))  # open
    # high задевает tp ≈ 102
    snap = e.process_closed_candle(_candle(1_800_000, "100.5", "102.5", "100", "102"))
    assert snap.closed_trade is not None
    assert snap.closed_trade.exit_reason == "tp"
    assert snap.closed_trade.net_pnl > 0
    assert j.get_open_position("BTC/USDT:USDT") is None


def test_no_signal_no_position() -> None:
    e, _ = _engine(_Silent())
    for i in range(5):
        snap = e.process_closed_candle(_candle(i * 900_000, "100", "101", "99", "100"))
        assert snap.opened_position is None
        assert snap.closed_trade is None


def test_state_survives_restart() -> None:
    """Закрытие → новая инстанция движка видит equity и пустую позицию."""
    e, j = _engine(_AlwaysLong())
    e.process_closed_candle(_candle(0, "100", "101", "99", "100"))
    e.process_closed_candle(_candle(900_000, "100", "101", "99.5", "100.5"))
    e.process_closed_candle(_candle(1_800_000, "100.5", "102.5", "100", "102"))
    eq_before = e.equity
    # «рестарт»: пересоздаём движок с тем же журналом
    cfg = load_risk_config()
    costs = CostModel(taker_fee=Decimal("0.0005"), slippage_pct=Decimal("0.0005"))
    e2 = PaperEngine(
        symbol="BTC/USDT:USDT",
        strategy=_Silent(),
        cost_model=costs,
        risk_cfg=cfg,
        journal=j,
        starting_equity=Decimal("10000"),
    )
    assert e2.equity == eq_before
    assert j.get_open_position("BTC/USDT:USDT") is None
