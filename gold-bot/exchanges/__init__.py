"""Биржевой слой gold-bot: единый интерфейс к BingX и Bybit.

Реэкспорт публичного API, чтобы вышестоящий код писал
`from exchanges import OrderRequest, ExchangeAdapter`.
"""

from __future__ import annotations

from exchanges.base import ExchangeAdapter, PriceLevel
from exchanges.errors import (
    AuthError,
    ExchangeError,
    InsufficientFunds,
    InvalidOrder,
    MarginModeError,
    NetworkError,
    RateLimitError,
)
from exchanges.models import (
    OHLCV,
    Balance,
    MarginMode,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    Ticker,
)

__all__ = [
    "OHLCV",
    "AuthError",
    "Balance",
    "ExchangeAdapter",
    "ExchangeError",
    "InsufficientFunds",
    "InvalidOrder",
    "MarginMode",
    "MarginModeError",
    "NetworkError",
    "OrderRequest",
    "OrderResult",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "PositionSide",
    "PriceLevel",
    "RateLimitError",
    "Ticker",
]
