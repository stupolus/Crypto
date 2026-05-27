"""Bybit V5 адаптер (план 49).

Фаза 49.1: public API + signing + settings. Private API — фаза 49.2.

CLAUDE.md: биржа №2 в трёх ролях — testnet smoke, live execution (после
testnet + явного «да»), источник ДАННЫХ для анализа/бэктеста.
"""

from adapters.bybit.client import BybitClient
from adapters.bybit.exceptions import APIError, AuthError, NetworkError
from adapters.bybit.models import Kline, Ticker
from adapters.bybit.public import PublicAPI
from adapters.bybit.settings import BybitSettings, load_settings
from adapters.bybit.signing import sign_query
from adapters.bybit.symbol import from_project_format, to_project_format

__all__ = [
    "APIError",
    "AuthError",
    "BybitClient",
    "BybitSettings",
    "Kline",
    "NetworkError",
    "PublicAPI",
    "Ticker",
    "from_project_format",
    "load_settings",
    "sign_query",
    "to_project_format",
]
