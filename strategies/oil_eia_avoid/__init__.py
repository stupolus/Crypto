"""OilEiaAvoid — CL-USDT (WTI crude), both-sided Donchian breakout 15m
с blackout вокруг EIA Petroleum Status Report (среда 14:30 UTC ±N).

Использует тот же ``BtcBreakoutStrategy`` (algorithm-generic) + EIA-aware
``NewsCalendar`` через DI. Обоснование параметров: ``plans/19-asset-strategies.md``.
"""

from strategies.btc_breakout import BtcBreakoutStrategy
from strategies.oil_eia_avoid.calendar import build_eia_news_calendar
from strategies.oil_eia_avoid.config import (
    StrategyConfigError,
    get_default_config,
    load_config,
)

__all__ = [
    "BtcBreakoutStrategy",
    "StrategyConfigError",
    "build_eia_news_calendar",
    "get_default_config",
    "load_config",
]
