"""BingX-адаптер (USDT-M perpetual).

Публичный API:
- Фаза 0.B: конфиг, базовый HTTP-клиент, публичные REST, WS-каркас (market).
- Фаза 0.C: pydantic-settings для ключей, приватные read + setters,
  server-time sync.

Размещение/отмена ордеров и kill switch — фаза 0.D, см.
``plans/01-bingx-адаптер.md`` §11.
"""

from adapters.bingx.client import BingXClient, sign_query
from adapters.bingx.config import BingXConfig, get_default_config, load_config
from adapters.bingx.exceptions import (
    APIError,
    AuthError,
    BingXError,
    ConfigError,
    InvalidResponseError,
    NetworkError,
    RateLimited,
    ServerError,
    WebSocketError,
)
from adapters.bingx.models import (
    AssetBalance,
    Contract,
    Fill,
    Kline,
    LeverageInfo,
    OpenOrder,
    Position,
    PositionMode,
    ServerTime,
    Ticker,
)
from adapters.bingx.private import PrivateAPI
from adapters.bingx.public import PublicAPI
from adapters.bingx.settings import BingXSettings, load_settings
from adapters.bingx.websocket import BingXMarketWebSocket

__all__ = [
    "APIError",
    "AssetBalance",
    "AuthError",
    "BingXClient",
    "BingXConfig",
    "BingXError",
    "BingXMarketWebSocket",
    "BingXSettings",
    "ConfigError",
    "Contract",
    "Fill",
    "InvalidResponseError",
    "Kline",
    "LeverageInfo",
    "NetworkError",
    "OpenOrder",
    "Position",
    "PositionMode",
    "PrivateAPI",
    "PublicAPI",
    "RateLimited",
    "ServerError",
    "ServerTime",
    "Ticker",
    "WebSocketError",
    "get_default_config",
    "load_config",
    "load_settings",
    "sign_query",
]
