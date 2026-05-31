"""Bybit V5 адаптер (план 49).

Фазы:
- 49.1: public API + signing + settings ✅
- 49.2: private API (balance, positions, orders) ✅
- 49.3: testnet smoke на VPS (нужны ключи владельца)
- 49.4: WebSocket user stream (опционально)
- 49.5: production hardening — снятие live-guard
- 49.6: cross-venue (Bybit-data → BingX-execution)
- 49.7: BybitDataSource для core/backtest (#181 уже добавил downloader)

CLAUDE.md: биржа №2 в трёх ролях — testnet smoke, live execution (после
testnet + явного «да»), источник ДАННЫХ для анализа/бэктеста.

⚠️ Live-trade hard-блокирован в private.PrivateAPI.place_order до фазы 49.5.
"""

from adapters.bybit.client import BybitClient
from adapters.bybit.exceptions import APIError, AuthError, NetworkError, RateLimited
from adapters.bybit.models import Kline, Ticker
from adapters.bybit.private import PrivateAPI
from adapters.bybit.private_models import (
    CoinBalance,
    OrderAck,
    Position,
)
from adapters.bybit.public import PublicAPI
from adapters.bybit.settings import BybitSettings, load_settings
from adapters.bybit.signing import sign_query
from adapters.bybit.symbol import from_project_format, to_project_format

__all__ = [
    "APIError",
    "AuthError",
    "BybitClient",
    "BybitSettings",
    "CoinBalance",
    "Kline",
    "NetworkError",
    "OrderAck",
    "Position",
    "PrivateAPI",
    "PublicAPI",
    "RateLimited",
    "Ticker",
    "from_project_format",
    "load_settings",
    "sign_query",
    "to_project_format",
]
