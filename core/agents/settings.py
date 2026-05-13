"""Конфиг агентов — Anthropic API ключ из .env.

Тот же паттерн что core.alerts.settings.TelegramSettings —
pydantic-settings автоматически загружает .env.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень репо: settings.py лежит в core/agents/, .env — в корне.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class AnthropicSettings(BaseSettings):
    """Источник Anthropic API ключа.

    Поле Optional — отсутствие ключа не должно ронять импорт.
    Проверка ленивая, в момент построения AgentTeam.
    """

    model_config = SettingsConfigDict(
        env_prefix="ANTHROPIC_",
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
