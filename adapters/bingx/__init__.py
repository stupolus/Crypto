"""BingX-адаптер (USDT-M perpetual).

Публичный API:
- Фаза 0.B — публичные REST (`PublicAPI`) + WS market data (`BingXMarketWebSocket`).
- Фаза 0.C — приватный read + idempotent setters (`PrivateAPI`).

Ордерные методы — фаза 0.D, см. ``plans/01-bingx-адаптер.md`` §11.
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
from adapters.bingx.models import Contract, Kline, ServerTime, Ticker
from adapters.bingx.private import PrivateAPI
from adapters.bingx.private_models import (
    Balance,
    EntryOrderType,
    Fill,
    MarginType,
    Order,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    TimeInForce,
)
from adapters.bingx.public import PublicAPI
from adapters.bingx.settings import BingXSettings, load_settings
from adapters.bingx.time_sync import ServerTimeSyncer
from adapters.bingx.websocket import BingXMarketWebSocket

__all__ = [
    "APIError",
    "AuthError",
    "Balance",
    "BingXClient",
    "BingXConfig",
    "BingXError",
    "BingXMarketWebSocket",
    "BingXSettings",
    "ConfigError",
    "Contract",
    "EntryOrderType",
    "Fill",
    "InvalidResponseError",
    "Kline",
    "MarginType",
    "NetworkError",
    "Order",
    "OrderRequest",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "PositionSide",
    "PrivateAPI",
    "PublicAPI",
    "RateLimited",
    "ServerError",
    "ServerTime",
    "ServerTimeSyncer",
    "Ticker",
    "TimeInForce",
    "WebSocketError",
    "get_default_config",
    "load_config",
    "load_settings",
    "sign_query",
]
