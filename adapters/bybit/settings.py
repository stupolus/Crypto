"""Чтение API-ключей Bybit из переменных окружения / ``.env``.

Принципы (CLAUDE.md, бизнес/риск-профиль.md):
- Ключи — только из env / ``.env`` (никогда из YAML, CLI, кода).
- Префикс ``BYBIT_`` отделяет наши переменные от чужих.
- Реальный ``.env`` всегда в ``.gitignore``; шаблон — ``.env.example``.
- Поля для testnet и live разнесены: одна пара ключей физически не
  может «случайно» уйти на другую среду — выбор делает свойство
  ``active_key``/``active_secret`` по полю ``env``.

Импорт модуля **не** требует ключей: ``BybitSettings`` валидируется
как пустой объект. Отсутствие ключей всплывёт только при попытке
signed-запроса через ``AuthError``.

См. план 49: до фазы 49.5 live-режим hard-блокирован для трейда
(проверки в private.py); read-only public-вызовы на live допустимы
для роли «источник данных» (см. план 49.7).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень репо: settings.py лежит в adapters/bybit/, .env — в корне.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class BybitSettings(BaseSettings):
    """Источник API-ключей Bybit.

    Конфиг:
    - ``env_prefix="BYBIT_"``: ``BYBIT_TESTNET_API_KEY`` → ``testnet_api_key``.
    - ``env_file=".env"`` в корне репо.
    - ``extra="ignore"``: чужие ``BYBIT_*`` переменные не ломают парсинг.
    - ``case_sensitive=False``.

    Поля ключей — ``str | None``: отсутствие ключа в .env не должно
    ронять импорт. Проверка делается лениво в момент обращения к
    ``active_*``.
    """

    model_config = SettingsConfigDict(
        env_prefix="BYBIT_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
    )

    env: Literal["testnet", "live"] = Field(default="testnet")
    testnet_api_key: str | None = Field(default=None)
    testnet_api_secret: str | None = Field(default=None)
    live_api_key: str | None = Field(default=None)
    live_api_secret: str | None = Field(default=None)
    recv_window_ms: int = Field(default=5000, ge=100, le=60_000)

    @property
    def active_key(self) -> str | None:
        """Ключ, соответствующий выбранному ``env``."""
        return self.testnet_api_key if self.env == "testnet" else self.live_api_key

    @property
    def active_secret(self) -> str | None:
        return self.testnet_api_secret if self.env == "testnet" else self.live_api_secret

    @property
    def rest_base_url(self) -> str:
        """Базовый REST URL по выбранному ``env``.

        Testnet:    api-testnet.bybit.com
        Live (mainnet): api.bybit.com
        """
        return "https://api-testnet.bybit.com" if self.env == "testnet" else "https://api.bybit.com"

    def has_credentials(self) -> bool:
        """Истинно, когда для активного окружения заданы и key, и secret."""
        return bool(self.active_key) and bool(self.active_secret)


def load_settings() -> BybitSettings:
    """Прочитать настройки из env/``.env``. Без кеша: ``.env`` мог быть обновлён."""
    return BybitSettings()
