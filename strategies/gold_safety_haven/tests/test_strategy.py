"""Тесты GoldSafetyHaven — проверяем что YAML валиден и long-only enforcement
работает на уровне алгоритма.
"""

from __future__ import annotations

from decimal import Decimal

from adapters.bingx.models import Kline
from core.backtest import StrategyContext
from core.risk import RiskEngine
from strategies.btc_breakout import BtcBreakoutStrategy
from strategies.btc_breakout.config import StrategyConfig
from strategies.gold_safety_haven import get_default_config


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


def _breakdown_history() -> list[Kline]:
    """Свечи с растущей волатильностью + breakdown вниз на последней."""
    candles: list[Kline] = []
    base = 2000  # gold-ish цена
    for i in range(25):
        amp = 5 + i * 0.5
        h = base + amp
        low = base - amp
        candles.append(
            _kline(
                i * 3_600_000,  # 1h
                str(base),
                f"{h:.4f}",
                f"{low:.4f}",
                str(base),
                volume="100",
            )
        )
    for i in range(25, 30):
        amp = 30.0
        candles.append(
            _kline(
                i * 3_600_000,
                str(base),
                f"{base + amp}",
                f"{base - amp}",
                str(base),
                volume="100",
            )
        )
    return candles


def test_default_config_loads_with_gold_params() -> None:
    cfg = get_default_config()
    assert cfg.symbol == "XAUT-USDT"
    assert cfg.timeframe == "1h"
    assert cfg.direction_bias == "long_only"
    assert cfg.donchian_n == 50
    assert cfg.tp1_r_multiple == 2.0


def test_long_only_blocks_short_breakdown() -> None:
    """Breakdown вниз → SELL не должен генериться при long_only."""
    cfg = get_default_config()
    # Урежем warmup-параметры чтобы влезли в синтетику.
    cfg_small = StrategyConfig.model_validate(
        {
            **cfg.model_dump(),
            "donchian_n": 5,
            "atr_window": 5,
            "atr_percentile_min": 0.0,  # отключим filter для упрощения
            "atr_percentile_lookback": 10,
            "volume_sma_window": 5,
            "volume_multiplier": 1.0,
        }
    )
    strategy = BtcBreakoutStrategy(config=cfg_small, risk_engine=RiskEngine())
    history = _breakdown_history()
    # Свеча breakdown вниз — close ниже Donchian-low.
    history.append(_kline(30 * 3_600_000, "2000", "2005", "1900", "1900", volume="500"))
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("10000"),
        open_position=None,
    )
    assert strategy.on_candle_close(ctx) is None


def test_long_only_allows_long_breakout() -> None:
    """Breakout вверх → BUY проходит."""
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
    strategy = BtcBreakoutStrategy(config=cfg_small, risk_engine=RiskEngine())
    history = _breakdown_history()
    # Свеча breakout вверх — close выше Donchian-high.
    history.append(_kline(30 * 3_600_000, "2000", "2100", "2000", "2100", volume="500"))
    ctx = StrategyContext(
        current_candle=history[-1],
        history=tuple(history),
        equity=Decimal("10000"),
        open_position=None,
    )
    signal = strategy.on_candle_close(ctx)
    assert signal is not None
    assert signal.side == "BUY"
