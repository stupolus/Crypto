"""StockEarningsAvoid — TSLA-USDT / NVDA-USDT (equity perps), both-sided
Donchian breakout 15m с blackout вокруг earnings releases.

Session enforcement (Mon-Fri 13:30-20:00 UTC) — через `core.assets`
registry (asset_class=stock_perp). Runner проверяет `is_session_open`
до вызова стратегии, поэтому здесь дополнительная проверка не нужна.

Обоснование параметров: ``plans/19-asset-strategies.md``.
"""

from strategies.btc_breakout import BtcBreakoutStrategy
from strategies.stock_earnings_avoid.calendar import (
    build_earnings_blackout_calendar,
)
from strategies.stock_earnings_avoid.config import (
    StrategyConfigError,
    get_default_config,
    load_config,
)

__all__ = [
    "BtcBreakoutStrategy",
    "StrategyConfigError",
    "build_earnings_blackout_calendar",
    "get_default_config",
    "load_config",
]
