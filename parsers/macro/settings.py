"""Конфиг macro-адаптеров — FRED API ключ из .env.

Паттерн повторяет ``core.agents.settings.AnthropicSettings`` —
pydantic-settings автоматически загружает ``.env`` из корня репо.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# settings.py лежит в parsers/macro/, .env — в корне репо.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class FREDSettings(BaseSettings):
    """Источник FRED API ключа.

    Поле Optional — отсутствие ключа не должно ронять импорт.
    Проверка ленивая, в момент построения FREDAdapter.
    """

    model_config = SettingsConfigDict(
        env_prefix="FRED_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
    )

    api_key: str | None = Field(default=None)

    @property
    def configured(self) -> bool:
        return bool(self.api_key)
