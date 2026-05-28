"""Адаптер Bybit (USDT-перпы, linear) поверх ccxt.

Bybit имеет публичный testnet (testnet.bybit.com) — используется в фазе 1F.
Клиента можно внедрить (для тестов), иначе создаётся ccxt.bybit.
"""

from __future__ import annotations

from typing import Any

import ccxt.async_support as ccxt_async

from exchanges.ccxt_base import CcxtAdapter


class BybitAdapter(CcxtAdapter):
    name: str = "bybit"

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        *,
        testnet: bool = False,
        client: Any | None = None,
    ) -> None:
        if client is None:
            client = ccxt_async.bybit(
                {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "enableRateLimit": True,
                    "options": {"defaultType": "swap"},
                }
            )
            if testnet:
                client.set_sandbox_mode(True)
        super().__init__(client)
