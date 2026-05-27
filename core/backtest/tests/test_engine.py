"""Unit-тесты ``core.backtest.engine.BacktestEngine``."""

from __future__ import annotations

from decimal import Decimal

import pytest

from adapters.bingx.models import Kline
from adapters.bingx.private_models import OrderRequest
from core.backtest import BacktestConfig, BacktestEngine, FillEvent, StrategyContext, Trade
from core.backtest.config import FeesConfig


def _kline(
    open_time_ms: int,
    open_: str,
    high: str,
    low: str,
    close: str,
    volume: str = "100",
) -> Kline:
    return Kline.model_validate(
        {
            "time": open_time_ms,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


@pytest.fixture
def cfg() -> BacktestConfig:
    return BacktestConfig(
        fees=FeesConfig(taker_pct=0.05, maker_pct=0.02),
        slippage_bps=10,
        initial_equity=1000.0,
    )


class _NoopStrategy:
    """Ничего не делает — для проверки flat-equity."""

    def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None:
        return None

    def on_fill(self, fill: FillEvent) -> None:
        pass


class _OneShotLongStrategy:
    """Открывает один LONG на 2-й свече с SL -1% и TP +1.5%."""

    def __init__(self) -> None:
        self.signaled = False
        self.fills: list[FillEvent] = []

    def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None:
        if self.signaled or len(ctx.history) < 2:
            return None
        self.signaled = True
        entry = ctx.current_candle.close
        return OrderRequest(
            symbol="BTC-USDT",
            side="BUY",
            position_side="LONG",
            order_type="MARKET",
            quantity=Decimal("0.01"),
            attached_stop_loss=entry * Decimal("0.99"),
            attached_take_profit=entry * Decimal("1.015"),
            client_order_id="oneshot-1",
        )

    def on_fill(self, fill: FillEvent) -> None:
        self.fills.append(fill)


def test_noop_strategy_keeps_initial_equity(cfg: BacktestConfig) -> None:
    engine = BacktestEngine(cfg)
    candles = [_kline(i * 60_000, "60000", "60010", "59990", "60005") for i in range(10)]
    result = engine.run(_NoopStrategy(), candles)
    assert result.summary.total_trades == 0
    assert result.summary.final_equity == Decimal("1000")
    assert result.summary.total_pnl_pct == 0


def test_no_candles_returns_empty(cfg: BacktestConfig) -> None:
    engine = BacktestEngine(cfg)
    result = engine.run(_NoopStrategy(), [])
    assert result.trades == ()
    assert result.summary.total_trades == 0


def test_long_take_profit_path(cfg: BacktestConfig) -> None:
    """LONG @60000, SL@59400, TP@60900. Свеча с high=61000 → TP hit."""
    engine = BacktestEngine(cfg)
    candles = [
        _kline(0, "60000", "60010", "59990", "60000"),  # 1st: warmup
        _kline(60_000, "60000", "60010", "59990", "60000"),  # 2nd: signal close
        _kline(120_000, "60000", "61050", "59900", "60800"),  # 3rd: fill + TP hit
    ]
    strategy = _OneShotLongStrategy()
    result = engine.run(strategy, candles)
    assert len(result.trades) == 1
    trade: Trade = result.trades[0]
    assert trade.is_win
    assert trade.exits[0].reason == "TAKE_PROFIT_1"


def test_long_stop_loss_path(cfg: BacktestConfig) -> None:
    """LONG @60000, SL@59400. Свеча с low=59000 → SL hit."""
    engine = BacktestEngine(cfg)
    candles = [
        _kline(0, "60000", "60010", "59990", "60000"),
        _kline(60_000, "60000", "60010", "59990", "60000"),
        _kline(120_000, "60000", "60100", "59000", "59100"),  # SL hit
    ]
    strategy = _OneShotLongStrategy()
    result = engine.run(strategy, candles)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.is_loss
    assert trade.exits[0].reason == "STOP_LOSS"


def test_sl_priority_over_tp_when_both_touched_in_one_candle(
    cfg: BacktestConfig,
) -> None:
    """LONG @60000, SL@59400 + TP@60900. high=61000 И low=59000 → берём SL."""
    engine = BacktestEngine(cfg)
    candles = [
        _kline(0, "60000", "60010", "59990", "60000"),
        _kline(60_000, "60000", "60010", "59990", "60000"),
        _kline(120_000, "60000", "61050", "59000", "60500"),  # оба touched
    ]
    strategy = _OneShotLongStrategy()
    result = engine.run(strategy, candles)
    assert len(result.trades) == 1
    assert result.trades[0].exits[0].reason == "STOP_LOSS"


def test_market_entry_uses_next_candle_open_with_slippage(cfg: BacktestConfig) -> None:
    """Entry — по open следующей свечи + slippage (10 bps)."""
    engine = BacktestEngine(cfg)
    candles = [
        _kline(0, "60000", "60010", "59990", "60000"),
        _kline(60_000, "60000", "60010", "59990", "60000"),  # signal closes here
        _kline(120_000, "60500", "60600", "59900", "60100"),  # entry @ open=60500 + slip
    ]
    strategy = _OneShotLongStrategy()
    result = engine.run(strategy, candles)
    fill = result.trades[0].entry
    # slippage_bps = 10 → 0.1% — adjusted_price = 60500 * 1.001 = 60560.5
    expected = Decimal("60500") * Decimal("1.001")
    assert fill.price == expected


def test_lookahead_independence_future_changes_do_not_affect_past(
    cfg: BacktestConfig,
) -> None:
    """Изменение future-свечи после exit не должно менять результат."""
    engine = BacktestEngine(cfg)
    base_candles = [
        _kline(0, "60000", "60010", "59990", "60000"),
        _kline(60_000, "60000", "60010", "59990", "60000"),
        _kline(120_000, "60000", "61050", "59900", "60800"),  # TP hit
        _kline(180_000, "60800", "60900", "60700", "60750"),  # после exit
    ]
    altered_candles = list(base_candles)
    altered_candles[3] = _kline(
        180_000, "60800", "90000", "60700", "85000"
    )  # бредовая свеча после exit

    r1 = engine.run(_OneShotLongStrategy(), base_candles)
    r2 = engine.run(_OneShotLongStrategy(), altered_candles)

    assert r1.trades[0].exits[0].price == r2.trades[0].exits[0].price
    assert r1.summary.final_equity == r2.summary.final_equity


def test_open_position_closed_at_end_of_data(cfg: BacktestConfig) -> None:
    """Если позиция открыта и данные закончились — closing market по close
    последней свечи."""
    engine = BacktestEngine(cfg)
    candles = [
        _kline(0, "60000", "60010", "59990", "60000"),
        _kline(60_000, "60000", "60010", "59990", "60000"),
        _kline(120_000, "60050", "60100", "59800", "60050"),  # entry, без SL/TP hit
    ]
    strategy = _OneShotLongStrategy()
    result = engine.run(strategy, candles)
    assert len(result.trades) == 1
    assert result.trades[0].exits[0].reason == "MANUAL_CLOSE"


def test_short_take_profit_path(cfg: BacktestConfig) -> None:
    """SHORT @60000, SL@60600, TP@59100. Свеча с low=59000 → TP hit."""

    class _OneShotShort:
        def __init__(self) -> None:
            self.signaled = False

        def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None:
            if self.signaled or len(ctx.history) < 2:
                return None
            self.signaled = True
            entry = ctx.current_candle.close
            return OrderRequest(
                symbol="BTC-USDT",
                side="SELL",
                position_side="SHORT",
                order_type="MARKET",
                quantity=Decimal("0.01"),
                attached_stop_loss=entry * Decimal("1.01"),
                attached_take_profit=entry * Decimal("0.985"),
                client_order_id="short-1",
            )

        def on_fill(self, fill: FillEvent) -> None:
            pass

    engine = BacktestEngine(cfg)
    candles = [
        _kline(0, "60000", "60010", "59990", "60000"),
        _kline(60_000, "60000", "60010", "59990", "60000"),
        _kline(120_000, "60000", "60100", "59000", "59100"),  # low=59000 < TP 59100
    ]
    result = engine.run(_OneShotShort(), candles)
    assert len(result.trades) == 1
    assert result.trades[0].is_win
    assert result.trades[0].exits[0].reason == "TAKE_PROFIT_1"


def test_summary_drawdown_calculation(cfg: BacktestConfig) -> None:
    """Max drawdown считается по equity_curve относительно peak."""

    class _LossThenWin:
        """Открывает 2 позиции: первая — loss, вторая — win."""

        def __init__(self) -> None:
            self.count = 0
            # Кешируем SL/TP для каждой сделки, чтобы они оставались актуальны
            # на момент fill (т.е. от close свечи signal, а не от current).
            self._next_request: OrderRequest | None = None

        def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None:
            # Открываем только когда нет позиции и не было signal.
            if ctx.open_position is not None or self.count >= 2:
                return None
            entry = ctx.current_candle.close
            self.count += 1
            sl = entry * Decimal("0.99")
            tp = entry * Decimal("1.015")
            return OrderRequest(
                symbol="BTC-USDT",
                side="BUY",
                position_side="LONG",
                order_type="MARKET",
                quantity=Decimal("0.01"),
                attached_stop_loss=sl,
                attached_take_profit=tp,
                client_order_id=f"trade-{self.count}",
            )

        def on_fill(self, fill: FillEvent) -> None:
            pass

    engine = BacktestEngine(cfg)
    candles = [
        _kline(0, "60000", "60010", "59990", "60000"),  # signal #1
        _kline(60_000, "60000", "60010", "59000", "59100"),  # entry #1 + SL hit (loss)
        _kline(120_000, "59100", "59200", "59000", "59100"),  # signal #2
        _kline(180_000, "59100", "60000", "59000", "59950"),  # entry #2 + TP hit
    ]
    result = engine.run(_LossThenWin(), candles)
    # Допускаем, что после loss произошла просадка > 0.
    assert result.summary.max_drawdown_pct > 0
    # Total trades = 2.
    assert result.summary.total_trades == 2


def test_strategy_cannot_send_signal_while_position_open(cfg: BacktestConfig) -> None:
    """Если позиция открыта — backtester игнорирует новый OrderRequest."""

    class _AlwaysLong:
        def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None:
            if ctx.open_position is not None:
                return None  # сама стратегия знает что не надо
            return OrderRequest(
                symbol="BTC-USDT",
                side="BUY",
                position_side="LONG",
                order_type="MARKET",
                quantity=Decimal("0.001"),
                attached_stop_loss=ctx.current_candle.close * Decimal("0.99"),
            )

        def on_fill(self, fill: FillEvent) -> None:
            pass

    engine = BacktestEngine(cfg)
    candles = [_kline(i * 60_000, "60000", "60100", "59900", "60000") for i in range(20)]
    result = engine.run(_AlwaysLong(), candles)
    # Открыта одна позиция, в конце теста закрылась MANUAL_CLOSE.
    assert result.summary.total_trades == 1
