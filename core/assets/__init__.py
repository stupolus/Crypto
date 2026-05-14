"""Asset class registry — типы инструментов и их session windows.

Поддерживаемые asset classes:
- crypto:    BTC, ETH, SOL, ... (BingX perpetuals). Торги 24/7
- commodity: XAU (gold), XAG (silver). Sun open → Fri close (CME-like)
- energy:    CL (WTI), NG (natural gas), BZ (Brent). Sessions + EIA pause
- stock_perp: TSLA, NVDA, AAPL (BingX stock perpetuals). US market hours

В config'е каждого asset:
- session_window: ((day_start, hh_start), (day_end, hh_end)) UTC
- max_leverage: int (cap для каждого класса)
- min_notional: Decimal (минимальный размер позиции в USDT)
- volatility_profile: "low" | "normal" | "high" (для размера риска)
"""

from core.assets.registry import (
    DEFAULT_REGISTRY,
    AssetClass,
    AssetConfig,
    AssetRegistry,
    SessionWindow,
    UnknownAssetError,
    is_session_open,
)

__all__ = [
    "DEFAULT_REGISTRY",
    "AssetClass",
    "AssetConfig",
    "AssetRegistry",
    "SessionWindow",
    "UnknownAssetError",
    "is_session_open",
]
