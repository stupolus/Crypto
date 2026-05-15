"""Тесты OilEiaAvoid — проверяем что YAML валиден и EIA blackout работает."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from adapters.bingx.models import Kline
from core.backtest import StrategyContext
from core.risk import RiskEngine
from strategies.btc_breakout import BtcBreakoutStrategy
from strategies.btc_breakout.config import StrategyConfig
from strategies.oil_eia_avoid import (
    build_eia_news_calendar,
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


def _ms(year: int, month: int, day: int, hour: int, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=UTC).timestamp() * 1000)


def _breakout_history(start_ts_ms: int, step_ms: int = 15 * 60_000) -> list[Kline]:
    """Свечи с растущей волатильностью + breakout на последней."""
    candles: list[Kline] = []
    base = 80  # WTI crude $80-ish
    for i in range(25):
        amp = 0.5 + i * 0.05
        h = base + amp
        low = base - amp
        candles.append(
            _kline(
                start_ts_ms + i * step_ms,
                str(base),
                f"{h:.4f}",
                f"{low:.4f}",
                str(base),
                volume="100",
            )
        )
    for i in range(25, 30):
        candles.append(
            _kline(
                start_ts_ms + i * step_ms,
                str(base),
                f"{base + 2.0}",
                f"{base - 2.0}",
                str(base),
                volume="100",
            )
        )
    return candles


def test_default_config_loads() -> None:
    cfg = get_default_config()
    assert cfg.symbol == "CL-USDT"
    assert cfg.timeframe == "15m"
    assert cfg.donchian_n == 20


def test_eia_calendar_pauses_wednesday_window() -> None:
    cal = build_eia_news_calendar()
    # Wed 2026-05-13 14:30 UTC — внутри EIA-окна
    assert cal.is_paused(_ms(2026, 5, 13, 14, 30)) is True
    # Tue 2026-05-12 14:30 — не среда
    assert cal.is_paused(_ms(2026, 5, 12, 14, 30)) is False


def test_eia_blackout_blocks_signal_on_wednesday() -> None:
    """Breakout срабатывал бы, но EIA-окно блокирует сделку."""
    cfg = get_default_config()
    # Урежем warmup для синтетики
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
        news_calendar=build_eia_news_calendar(),
    )
    # История начинается так, чтобы breakout-свеча попала в Wed 14:30 UTC.
    wed_window_ts = _ms(2026, 5, 13, 14, 30)
    history = _breakout_history(wed_window_ts - 30 * 15 * 60_000)
    history.append(_kline(wed_window_ts, "80", "85", "80", "85", volume="500"))
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("10000"),
        open_position=None,
    )
    # EIA blackout → no signal
    assert strategy.on_candle_close(ctx) is None


def test_signal_allowed_outside_eia_blackout() -> None:
    """Тот же breakout, но в понедельник — EIA календарь не блокирует."""
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
        news_calendar=build_eia_news_calendar(),
    )
    # Mon 2026-05-11 12:00 UTC — вне EIA-окна
    mon_ts = _ms(2026, 5, 11, 12, 0)
    history = _breakout_history(mon_ts - 30 * 15 * 60_000)
    history.append(_kline(mon_ts, "80", "85", "80", "85", volume="500"))
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("10000"),
        open_position=None,
    )
    signal = strategy.on_candle_close(ctx)
    assert signal is not None
    assert signal.side == "BUY"
