"""Настройки Telegram alerter — загрузка из .env через pydantic-settings.

Без этого `os.getenv()` не видит .env (нужно загружать вручную).
Pydantic-settings делает это автоматически, как BingXSettings.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Тот же путь что BingXSettings.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class TelegramSettings(BaseSettings):
    """Источник Telegram токенов из .env / окружения.

    Поля Optional — отсутствие токена не должно ронять старт runner'а;
    тогда возвращаем StdoutAlerter.
    """

    model_config = SettingsConfigDict(
        env_prefix="TELEGRAM_",
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
    )

    bot_token: str | None = Field(default=None)
    chat_id: str | None = Field(default=None)

    @property
    def configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)
