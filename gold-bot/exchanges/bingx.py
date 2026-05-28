"""Адаптер BingX (USDT-перпы) поверх ccxt.

BingX имеет VST (demo / виртуальные средства) — отдельный endpoint
open-api-vst.bingx.com через ccxt sandbox mode. По умолчанию vst=True
(безопасный дефолт, см. CLAUDE.md §9). Live — только явным vst=False.
Клиента можно внедрить (для тестов), иначе создаётся ccxt.bingx.
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
        vst: bool = True,
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
            if vst:
                client.set_sandbox_mode(True)
        super().__init__(client)
