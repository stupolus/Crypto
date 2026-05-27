"""Bybit API settings из .env (gitignored).

Ключи опциональны для публичных эндпоинтов (без auth тоже работают,
но с более жёсткими rate-limits). Private/trading тут НЕ
используются — это data-only пакет.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class BybitSettings(BaseSettings):
    """``BYBIT_*`` из .env.

    - ``BYBIT_ENV``: ``mainnet`` (api.bybit.com), ``demo``
      (api-demo.bybit.com), ``testnet`` (api-testnet.bybit.com).
    - ``BYBIT_API_KEY``: опционально, для повышения rate-limit
      публичных запросов (передаётся в заголовке ``X-BAPI-API-KEY``,
      БЕЗ HMAC-подписи).
    """

    model_config = SettingsConfigDict(
        env_prefix="BYBIT_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    env: Literal["mainnet", "demo", "testnet"] = "mainnet"
    api_key: str | None = Field(default=None)
    api_secret: str | None = Field(default=None)

    @property
    def base_url(self) -> str:
        return {
            "mainnet": "https://api.bybit.com",
            "demo": "https://api-demo.bybit.com",
            "testnet": "https://api-testnet.bybit.com",
        }[self.env]
