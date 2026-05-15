"""Тесты StockEarningsAvoid."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from adapters.bingx.models import Kline
from core.backtest import StrategyContext
from core.risk import RiskEngine
from strategies.btc_breakout import BtcBreakoutStrategy
from strategies.btc_breakout.config import StrategyConfig
from strategies.stock_earnings_avoid import (
    build_earnings_blackout_calendar,
    get_default_config,
)


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


def _ms(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp() * 1000)


def _breakout_history(start_ts_ms: int, step_ms: int = 15 * 60_000) -> list[Kline]:
    candles: list[Kline] = []
    base = 250  # TSLA-ish цена
    for i in range(25):
        amp = 1.0 + i * 0.1
        candles.append(
            _kline(
                start_ts_ms + i * step_ms,
                str(base),
                f"{base + amp:.4f}",
                f"{base - amp:.4f}",
                str(base),
                volume="100",
            )
        )
    for i in range(25, 30):
        candles.append(
            _kline(
                start_ts_ms + i * step_ms,
                str(base),
                f"{base + 5.0}",
                f"{base - 5.0}",
                str(base),
                volume="100",
            )
        )
    return candles


def test_default_config_loads() -> None:
    cfg = get_default_config()
    assert cfg.symbol == "NCSKTSLA2USD-USDT"
    assert cfg.timeframe == "15m"
    assert cfg.donchian_n == 16


def test_earnings_calendar_blocks_during_window() -> None:
    """Earnings date 2026-07-23 → blackout 2026-07-21..2026-07-25 включительно."""
    cal = build_earnings_blackout_calendar("TSLA-USDT")
    # На earnings day
    assert cal.is_paused(_ms(2026, 7, 23)) is True
    # ±2 дня
    assert cal.is_paused(_ms(2026, 7, 21)) is True
    assert cal.is_paused(_ms(2026, 7, 25, hour=23, minute=59)) is True
    # Вне окна
    assert cal.is_paused(_ms(2026, 7, 20)) is False
    assert cal.is_paused(_ms(2026, 7, 26, hour=1)) is False


def test_earnings_calendar_custom_dates_and_window() -> None:
    cal = build_earnings_blackout_calendar(
        "FOO-USDT",
        earnings_dates=("2026-06-15",),
        blackout_days=1,
    )
    assert cal.is_paused(_ms(2026, 6, 14)) is True
    assert cal.is_paused(_ms(2026, 6, 16, hour=23)) is True
    assert cal.is_paused(_ms(2026, 6, 13, hour=23, minute=59)) is False


def test_earnings_blackout_blocks_signal() -> None:
    """Breakout срабатывал бы, но earnings blackout блокирует сделку."""
    cfg = get_default_config()
    cfg_small = StrategyConfig.model_validate(
        {
            **cfg.model_dump(),
            "donchian_n": 5,
            "atr_window": 5,
            "atr_percentile_min": 0.0,
            "atr_percentile_lookback": 10,
            "volume_sma_window": 5,
            "volume_multiplier": 1.0,
        }
    )
    strategy = BtcBreakoutStrategy(
        config=cfg_small,
        risk_engine=RiskEngine(),
        news_calendar=build_earnings_blackout_calendar("TSLA-USDT"),
    )
    # 2026-07-23 — TSLA earnings day
    ts = _ms(2026, 7, 23, hour=15)
    history = _breakout_history(ts - 30 * 15 * 60_000)
    history.append(_kline(ts, "250", "260", "250", "260", volume="500"))
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("10000"),
        open_position=None,
    )
    assert strategy.on_candle_close(ctx) is None


def test_signal_allowed_outside_earnings_window() -> None:
    """За неделю до earnings — сигнал проходит."""
    cfg = get_default_config()
    cfg_small = StrategyConfig.model_validate(
        {
            **cfg.model_dump(),
            "donchian_n": 5,
            "atr_window": 5,
            "atr_percentile_min": 0.0,
            "atr_percentile_lookback": 10,
            "volume_sma_window": 5,
            "volume_multiplier": 1.0,
        }
    )
    strategy = BtcBreakoutStrategy(
        config=cfg_small,
        risk_engine=RiskEngine(),
        news_calendar=build_earnings_blackout_calendar("TSLA-USDT"),
    )
    # За неделю до earnings 2026-07-23
    ts = _ms(2026, 7, 16, hour=15)
    history = _breakout_history(ts - 30 * 15 * 60_000)
    history.append(_kline(ts, "250", "260", "250", "260", volume="500"))
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("10000"),
        open_position=None,
    )
    signal = strategy.on_candle_close(ctx)
    assert signal is not None
    assert signal.side == "BUY"
