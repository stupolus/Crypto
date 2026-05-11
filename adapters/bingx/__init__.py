"""BingX-адаптер (USDT-M perpetual).

Публичный API фазы 0.B: загрузка конфига, базовый HTTP-клиент и
типизированные публичные REST-методы, плюс WS-каркас на market data.

Приватные эндпоинты (баланс, позиции, ордера) — фаза 0.C/0.D, см.
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
from adapters.bingx.models import Contract, Kline, ServerTime, Ticker
from adapters.bingx.public import PublicAPI
from adapters.bingx.websocket import BingXMarketWebSocket

__all__ = [
    "APIError",
    "AuthError",
    "BingXClient",
    "BingXConfig",
    "BingXError",
    "BingXMarketWebSocket",
    "ConfigError",
    "Contract",
    "InvalidResponseError",
    "Kline",
    "NetworkError",
    "PublicAPI",
    "RateLimited",
    "ServerError",
    "ServerTime",
    "Ticker",
    "WebSocketError",
    "get_default_config",
    "load_config",
    "sign_query",
]
