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
    OrderRejected,
    RateLimited,
    ServerError,
    WebSocketError,
)
from adapters.bingx.journal import JournalEntry, OrderJournal
from adapters.bingx.metrics import MetricsWriter, OrderMetric, compute_slippage_bps
from adapters.bingx.models import Contract, Kline, ServerTime, Ticker
from adapters.bingx.private import PrivateAPI
from adapters.bingx.private_models import (
    AccountUpdateEvent,
    Balance,
    BalanceDelta,
    EntryOrderType,
    Fill,
    MarginType,
    Order,
    OrderAck,
    OrderRequest,
    OrderSide,
    OrderStatus,
    OrderType,
    OrderUpdateEvent,
    Position,
    PositionDelta,
    PositionSide,
    TimeInForce,
    UserStreamEvent,
    UserStreamReconcileEvent,
    parse_user_stream_event,
)
from adapters.bingx.public import PublicAPI
from adapters.bingx.settings import BingXSettings, load_settings
from adapters.bingx.time_sync import ServerTimeSyncer
from adapters.bingx.user_stream import BingXUserDataStream
from adapters.bingx.websocket import BingXMarketWebSocket

__all__ = [
    "APIError",
    "AccountUpdateEvent",
    "AuthError",
    "Balance",
    "BalanceDelta",
    "BingXClient",
    "BingXConfig",
    "BingXError",
    "BingXMarketWebSocket",
    "BingXSettings",
    "BingXUserDataStream",
    "ConfigError",
    "Contract",
    "EntryOrderType",
    "Fill",
    "InvalidResponseError",
    "JournalEntry",
    "Kline",
    "MarginType",
    "MetricsWriter",
    "NetworkError",
    "Order",
    "OrderAck",
    "OrderJournal",
    "OrderMetric",
    "OrderRejected",
    "OrderRequest",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "OrderUpdateEvent",
    "Position",
    "PositionDelta",
    "PositionSide",
    "PrivateAPI",
    "PublicAPI",
    "RateLimited",
    "ServerError",
    "ServerTime",
    "ServerTimeSyncer",
    "Ticker",
    "TimeInForce",
    "UserStreamEvent",
    "UserStreamReconcileEvent",
    "WebSocketError",
    "compute_slippage_bps",
    "get_default_config",
    "load_config",
    "load_settings",
    "parse_user_stream_event",
    "sign_query",
]
