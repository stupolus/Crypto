"""Unit-тесты ``BtcBreakoutStrategy``.

Не подгоняем параметры — тесты проверяют **логику**, не результат.
Реальный edge — на бэктесте против истории (отдельная задача).
"""

from __future__ import annotations

from decimal import Decimal

from adapters.bingx.models import Kline
from core.backtest import BacktestEngine, FillEvent, StrategyContext
from core.risk import RiskEngine
from core.signals import (
    SetBlacklist,
    StaticFundingProvider,
    StaticNewsCalendar,
)
from strategies.btc_breakout import BtcBreakoutStrategy
from strategies.btc_breakout.config import StrategyConfig


def _make_config(**overrides: object) -> StrategyConfig:
    base: dict[str, object] = {
        "symbol": "BTC-USDT",
        "timeframe": "15m",
        "donchian_n": 5,
        "atr_window": 5,
        "atr_percentile_min": 0.5,
        "atr_percentile_lookback": 10,
        "volume_sma_window": 5,
        "volume_multiplier": 1.5,
        "funding_rate_max_pct": 0.05,
        "stop_min_pct": 0.5,
        "tp1_r_multiple": 1.5,
        "tp2_trailing_ema": 21,
        "risk_tier": "B",
    }
    base.update(overrides)
    return StrategyConfig.model_validate(base)


def _kline(t: int, open_: str, high: str, low: str, close: str, volume: str = "100") -> Kline:
    return Kline.model_validate(
        {
            "time": t,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def _make_strategy(**kwargs: object) -> BtcBreakoutStrategy:
    return BtcBreakoutStrategy(
        config=_make_config(**kwargs),
        risk_engine=RiskEngine(),
    )


# ── No-signal scenarios ──────────────────────────────────────────────────


def test_no_signal_during_warmup() -> None:
    strategy = _make_strategy()
    # 5 свечей < минимума (donchian 5 + lookback 10 + buffer).
    history = tuple(_kline(i, "100", "101", "99", "100") for i in range(3))
    ctx = StrategyContext(
        current_candle=history[-1],
        history=history,
        equity=Decimal("1000"),
        open_position=None,
    )
    assert strategy.on_candle_close(ctx) is None


def test_no_signal_when_no_breakout() -> None:
    """Цены в узком коридоре — Donchian не пробивается."""
    strategy = _make_strategy()
    history = tuple(_kline(i, "100", "101", "99", "100", volume="100") for i in range(30))
    ctx = StrategyContext(
        current_candle=history[-1],
        history=history,
        equity=Decimal("1000"),
        open_position=None,
    )
    assert strategy.on_candle_close(ctx) is None


# ── Signal scenarios ─────────────────────────────────────────────────────


def _breakout_history() -> list[Kline]:
    """30 свечей с растущей волатильностью + breakout на последней."""
    candles: list[Kline] = []
    base = 100
    # 25 свечей с постепенно нарастающей amplitude — даёт ATR-percentile рост.
    for i in range(25):
        amp = 1 + i * 0.05
        h = base + amp
        low = base - amp
        candles.append(
            _kline(
                i * 60_000,
                str(base),
                f"{h:.4f}",
                f"{low:.4f}",
                str(base),
                volume="100",
            )
        )
    # 5 свечей с разогрева волатильности — высокая ATR.
    for i in range(25, 30):
        amp = 3.0
        candles.append(
            _kline(
                i * 60_000,
                str(base),
                f"{base + amp}",
                f"{base - amp}",
                str(base),
                volume="100",
            )
        )
    return candles


def test_signal_triggered_on_breakout_with_volume() -> None:
    """Donchian пробит + объём 2× SMA + ATR в верхнем percentile."""
    strategy = _make_strategy()
    history = _breakout_history()
    # Последняя свеча: breakout вверх + большой volume.
    history.append(
        _kline(
            30 * 60_000,
            "100",
            "110",
            "100",
            "108",
            volume="500",  # SMA20-volume = 100 → 5× > 1.5×
        )
    )
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("1000"),
        open_position=None,
    )
    signal = strategy.on_candle_close(ctx)
    assert signal is not None
    assert signal.side == "BUY"
    assert signal.attached_stop_loss is not None
    assert signal.attached_stop_loss < signal.price if signal.price else True
    assert signal.attached_take_profit is not None


def test_signal_blocked_by_low_volume() -> None:
    """Та же setup, но volume = 50 (ниже SMA) → no signal."""
    strategy = _make_strategy()
    history = _breakout_history()
    history.append(
        _kline(30 * 60_000, "100", "110", "100", "108", volume="50"),
    )
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("1000"),
        open_position=None,
    )
    assert strategy.on_candle_close(ctx) is None


def test_signal_blocked_by_blacklist() -> None:
    strategy = BtcBreakoutStrategy(
        config=_make_config(),
        risk_engine=RiskEngine(),
        blacklist=SetBlacklist({"BTC-USDT"}),
    )
    history = _breakout_history()
    history.append(
        _kline(30 * 60_000, "100", "110", "100", "108", volume="500"),
    )
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("1000"),
        open_position=None,
    )
    assert strategy.on_candle_close(ctx) is None


def test_signal_blocked_by_news_pause() -> None:
    """News pause покрывает текущий момент."""
    history = _breakout_history()
    history.append(
        _kline(30 * 60_000, "100", "110", "100", "108", volume="500"),
    )
    strategy = BtcBreakoutStrategy(
        config=_make_config(),
        risk_engine=RiskEngine(),
        news_calendar=StaticNewsCalendar(pause_windows=[(29 * 60_000, 31 * 60_000)]),
    )
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("1000"),
        open_position=None,
    )
    assert strategy.on_candle_close(ctx) is None


def test_signal_blocked_by_funding_long() -> None:
    """LONG: funding > +0.05% → блок."""
    history = _breakout_history()
    history.append(
        _kline(30 * 60_000, "100", "110", "100", "108", volume="500"),
    )
    strategy = BtcBreakoutStrategy(
        config=_make_config(),
        risk_engine=RiskEngine(),
        funding_provider=StaticFundingProvider({"BTC-USDT": Decimal("0.001")}),  # 0.1%
    )
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("1000"),
        open_position=None,
    )
    assert strategy.on_candle_close(ctx) is None


def test_no_new_signal_while_position_open() -> None:
    """Когда open_position != None, стратегия не возвращает OrderRequest."""
    from core.backtest.models import OpenPosition

    strategy = _make_strategy()
    history = _breakout_history()
    history.append(
        _kline(30 * 60_000, "100", "110", "100", "108", volume="500"),
    )
    open_pos = OpenPosition(
        entry_price=Decimal("100"),
        quantity=Decimal("0.01"),
        side="BUY",
        stop_price=Decimal("99"),
        take_profit_price=Decimal("101.5"),
        entry_time_ms=29 * 60_000,
    )
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("1000"),
        open_position=open_pos,
    )
    assert strategy.on_candle_close(ctx) is None


# ── Integration с BacktestEngine ─────────────────────────────────────────


def test_strategy_runs_through_backtest_engine() -> None:
    """Smoke: стратегия не падает в backtest на синтетических данных."""
    strategy = _make_strategy()
    engine = BacktestEngine()
    candles = _breakout_history()
    # Добавим reversion-свечу для exit.
    candles.append(
        _kline(30 * 60_000, "100", "110", "100", "108", volume="500"),
    )
    candles.append(
        _kline(31 * 60_000, "108", "112", "107", "111.7"),  # TP1 hit (1.5R)
    )
    result = engine.run(strategy, candles)
    # 0 или 1 сделка — зависит от точных параметров. Главное — не падает.
    assert result.summary.total_trades >= 0


def test_consecutive_losses_counter() -> None:
    """on_fill(STOP_LOSS) увеличивает counter; on_fill(TAKE_PROFIT) сбрасывает."""
    strategy = _make_strategy()
    entry_fill = FillEvent(
        timestamp_ms=0,
        side="BUY",
        price=Decimal("100"),
        quantity=Decimal("0.01"),
        fee=Decimal("0"),
        reason="ENTRY",
    )
    strategy.on_fill(entry_fill)
    strategy.on_fill(
        FillEvent(
            timestamp_ms=60_000,
            side="SELL",
            price=Decimal("99"),
            quantity=Decimal("0.01"),
            fee=Decimal("0"),
            reason="STOP_LOSS",
        )
    )
    assert strategy._consecutive_losses == 1
    strategy.on_fill(
        FillEvent(
            timestamp_ms=120_000,
            side="BUY",
            price=Decimal("100"),
            quantity=Decimal("0.01"),
            fee=Decimal("0"),
            reason="ENTRY",
        )
    )
    strategy.on_fill(
        FillEvent(
            timestamp_ms=180_000,
            side="SELL",
            price=Decimal("101.5"),
            quantity=Decimal("0.01"),
            fee=Decimal("0"),
            reason="TAKE_PROFIT_1",
        )
    )
    assert strategy._consecutive_losses == 0


def test_protocol_compliance() -> None:
    """Стратегия должна соответствовать backtest Strategy protocol."""
    from core.backtest import Strategy

    strategy = _make_strategy()
    assert isinstance(strategy, Strategy)


# ── direction_bias ────────────────────────────────────────────────────────


def test_direction_bias_default_is_both() -> None:
    cfg = _make_config()
    assert cfg.direction_bias == "both"


def test_direction_bias_long_only_blocks_short_signal() -> None:
    """direction_bias='long_only' → SELL trigger игнорируется."""
    strategy = BtcBreakoutStrategy(
        config=_make_config(direction_bias="long_only"),
        risk_engine=RiskEngine(),
    )
    history = _breakout_history()
    # Breakdown вниз: close ниже Donchian-low.
    history.append(_kline(30 * 60_000, "100", "100", "90", "90", volume="500"))
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("1000"),
        open_position=None,
    )
    assert strategy.on_candle_close(ctx) is None


def test_direction_bias_short_only_blocks_long_signal() -> None:
    """direction_bias='short_only' → BUY trigger игнорируется."""
    strategy = BtcBreakoutStrategy(
        config=_make_config(direction_bias="short_only"),
        risk_engine=RiskEngine(),
    )
    history = _breakout_history()
    history.append(_kline(30 * 60_000, "100", "110", "100", "108", volume="500"))
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("1000"),
        open_position=None,
    )
    assert strategy.on_candle_close(ctx) is None
