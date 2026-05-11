"""Чтение API-ключей BingX из переменных окружения.

Принципы (см. CLAUDE.md §«Правила безопасности»):
- Ключи — только через env (``.env`` загружается pydantic-settings).
- Адаптер сам никогда не пишет ключи в логи (см. ``client.py``).
- Live и VST ключи разные; адаптер выбирает пару по ``env`` в YAML-конфиге.
- Если пары ключей для активного окружения нет — это явная ошибка конфигурации,
  а не fallback на публичный режим. Приватные методы не должны падать в рантайме
  с auth-ошибкой; они должны вообще не инициализироваться.
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from adapters.bingx.exceptions import ConfigError


class BingXSettings(BaseSettings):
    """Источник секретов: ``.env`` в корне репозитория и/или переменные окружения.

    Конструкция парная (live + vst), чтобы переключать ``env`` в YAML без
    перенакатки `.env`. Все поля Optional — отсутствие ключей это валидное
    состояние (например, фаза 0.B без приватного API).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    live_api_key: SecretStr | None = Field(default=None, alias="BINGX_LIVE_API_KEY")
    live_api_secret: SecretStr | None = Field(default=None, alias="BINGX_LIVE_API_SECRET")
    vst_api_key: SecretStr | None = Field(default=None, alias="BINGX_VST_API_KEY")
    vst_api_secret: SecretStr | None = Field(default=None, alias="BINGX_VST_API_SECRET")

    def credentials_for(self, env: str) -> tuple[str, str]:
        """Вернуть (api_key, api_secret) для целевого окружения.

        Бросает ConfigError если хотя бы один ключ пары отсутствует —
        приватный клиент не должен запускаться с половинными ключами.
        """
        if env == "live":
            key, secret = self.live_api_key, self.live_api_secret
            label = "BINGX_LIVE_API_KEY / BINGX_LIVE_API_SECRET"
        elif env == "vst":
            key, secret = self.vst_api_key, self.vst_api_secret
            label = "BINGX_VST_API_KEY / BINGX_VST_API_SECRET"
        else:
            raise ConfigError(f"unsupported env {env!r}; expected 'live' or 'vst'")
        if key is None or secret is None:
            raise ConfigError(
                f"BingX credentials for env={env!r} are missing; "
                f"set {label} in environment or .env"
            )
        return key.get_secret_value(), secret.get_secret_value()

    def has_credentials_for(self, env: str) -> bool:
        """Быстрая проверка наличия ключей без бросания исключения.

        Используется в тестах и условном bootstrap.
        """
        if env == "live":
            return self.live_api_key is not None and self.live_api_secret is not None
        if env == "vst":
            return self.vst_api_key is not None and self.vst_api_secret is not None
        return False


def load_settings() -> BingXSettings:
    """Прочитать ``.env`` + env vars. Без аргументов — фабрика по умолчанию."""
    return BingXSettings()
