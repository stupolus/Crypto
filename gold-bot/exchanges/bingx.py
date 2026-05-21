"""Адаптер BingX (USDT-перпы) поверх ccxt.

BingX не имеет полноценного публичного testnet — в фазе 1F работаем в
dry-run/paper. Клиента можно внедрить (для тестов), иначе создаётся ccxt.bingx.
"""

from __future__ import annotations

from typing import Any

import ccxt.async_support as ccxt_async

from exchanges.ccxt_base import CcxtAdapter


class BingXAdapter(CcxtAdapter):
    name: str = "bingx"

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        *,
        client: Any | None = None,
    ) -> None:
        if client is None:
            client = ccxt_async.bingx(
                {
                    "apiKey": api_key,
                    "secret": api_secret,
                    "enableRateLimit": True,
                    "options": {"defaultType": "swap"},
                }
            )
        super().__init__(client)
