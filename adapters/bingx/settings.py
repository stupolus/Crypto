"""Чтение API-ключей BingX из переменных окружения / ``.env``.

Принципы (CLAUDE.md, бизнес/риск-профиль.md):
- Ключи — только из env / ``.env`` (никогда из YAML, CLI, кода).
- Префикс ``BINGX_`` отделяет наши переменные от чужих.
- Реальный ``.env`` всегда в ``.gitignore``; шаблон — ``.env.example``.
- Поля для VST и live разнесены: одна пара ключей физически не может
  «случайно» сходить на другую среду — выбор делает свойство
  ``active_key``/``active_secret`` по полю ``env``.

Импорт этого модуля **не** требует наличия ключей. ``BingXSettings``
валидируется как пустой объект; отсутствие ключей всплывёт только при
попытке ``BingXClient.request_signed`` через ``AuthError``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень репо: settings.py лежит в adapters/bingx/, .env — в корне.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class BingXSettings(BaseSettings):
    """Источник API-ключей BingX.

    Конфиг:
    - ``env_prefix="BINGX_"``: ``BINGX_VST_API_KEY`` → ``vst_api_key``.
    - ``env_file=".env"`` в корне репо: для локальной разработки и VPS.
    - ``extra="ignore"``: чужие ``BINGX_*``-переменные не ломают парсинг.
    - ``case_sensitive=False``: BINGX_ENV / bingx_env равнозначны.

    Поля ключей — ``str | None``: отсутствие ключа в .env не должно ронять
    импорт. Проверка делается лениво в момент обращения к ``active_*``.
    """

    model_config = SettingsConfigDict(
        env_prefix="BINGX_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
    )

    env: Literal["vst", "live"] = Field(default="vst")
    vst_api_key: str | None = Field(default=None)
    vst_api_secret: str | None = Field(default=None)
    live_api_key: str | None = Field(default=None)
    live_api_secret: str | None = Field(default=None)

    @property
    def active_key(self) -> str | None:
        """Ключ, соответствующий выбранному ``env``."""
        return self.vst_api_key if self.env == "vst" else self.live_api_key

    @property
    def active_secret(self) -> str | None:
        return self.vst_api_secret if self.env == "vst" else self.live_api_secret

    def has_credentials(self) -> bool:
        """Истинно, когда для активного окружения заданы и key, и secret."""
        return bool(self.active_key) and bool(self.active_secret)


def load_settings() -> BingXSettings:
    """Прочитать настройки из env/``.env``. Без кеша: ``.env`` мог быть обновлён."""
    return BingXSettings()
