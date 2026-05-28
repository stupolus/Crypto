"""Структурное логирование + маскирование секретов.

`mask_secrets` — security-critical: гарантирует, что API-ключи/секреты не
утекут в логи. Реализовано на stdlib `logging` (без тяжёлых зависимостей),
вывод — JSON. structlog не используем, чтобы не тянуть зависимость в ядро;
при необходимости слой можно заменить позже без изменения вызовов.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable

MASK = "***"
LOGGER_NAME = "gold_bot"


def mask_secrets(text: str, secrets: Iterable[str]) -> str:
    """Заменить каждое вхождение непустого секрета на `***`."""
    masked = text
    for secret in secrets:
        if secret:  # пустые/None-подобные игнорируем, иначе затрём весь текст
            masked = masked.replace(secret, MASK)
    return masked


class SecretFilter(logging.Filter):
    """logging-фильтр, маскирующий секреты в финальном сообщении записи."""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets: list[str] = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        if self._secrets:
            record.msg = mask_secrets(record.getMessage(), self._secrets)
            record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """Минимальный JSON-форматтер для структурных логов."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    level: int = logging.INFO,
    secrets: Iterable[str] | None = None,
) -> logging.Logger:
    """Настроить логгер gold_bot: JSON-формат + опциональное маскирование."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    if secrets:
        handler.addFilter(SecretFilter(secrets))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
