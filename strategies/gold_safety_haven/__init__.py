"""GoldSafetyHaven — XAU-USDT, LONG-only Donchian breakout (1h).

Использует ту же ``BtcBreakoutStrategy`` (algorithm-generic), но с собственным
config: широкий Donchian (50 свечей на 1h ≈ 2 суток), long_only bias, более
строгий ATR-percentile (≥0.6), удлинённый TP1 (2R).

Обоснование параметров: ``plans/19-asset-strategies.md`` §«Gold».
"""

from strategies.btc_breakout import BtcBreakoutStrategy
from strategies.gold_safety_haven.config import (
    StrategyConfigError,
    get_default_config,
    load_config,
)

__all__ = [
    "BtcBreakoutStrategy",
    "StrategyConfigError",
    "get_default_config",
    "load_config",
]
