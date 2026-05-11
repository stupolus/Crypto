"""Notification channels: stdout (default) + Telegram (skeleton).

Generic интерфейс для алертов о критичных событиях. Стратегия / runner
зовут `alerter.send_critical(msg)` — фактический канал доставки
подменяется через DI.

На MVP — только `StdoutAlerter` (печать в лог уровня CRITICAL).
`TelegramAlerter` — каркас, требует bot token + chat_id (отложено).
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@runtime_checkable
class Alerter(Protocol):
    """Generic notification channel.

    Имплементации: ``StdoutAlerter`` (default), ``TelegramAlerter``
    (опционально, требует токен).
    """

    async def send(self, severity: Severity, message: str) -> None: ...

    async def send_info(self, message: str) -> None: ...

    async def send_warning(self, message: str) -> None: ...

    async def send_critical(self, message: str) -> None: ...


class StdoutAlerter:
    """Default alerter — пишет в `logging` с соответствующим уровнем.

    Подходит для dev/staging. На VPS логи pipe-ятся в файл/systemd
    journald, мониторинг видит критичные события через `journalctl`.
    """

    async def send(self, severity: Severity, message: str) -> None:
        level = {
            Severity.INFO: logging.INFO,
            Severity.WARNING: logging.WARNING,
            Severity.CRITICAL: logging.CRITICAL,
        }[severity]
        logger.log(level, "[ALERT] %s", message)

    async def send_info(self, message: str) -> None:
        await self.send(Severity.INFO, message)

    async def send_warning(self, message: str) -> None:
        await self.send(Severity.WARNING, message)

    async def send_critical(self, message: str) -> None:
        await self.send(Severity.CRITICAL, message)


class NoopAlerter:
    """Полная заглушка — для тестов где алерты не интересны."""

    async def send(self, severity: Severity, message: str) -> None:
        return

    async def send_info(self, message: str) -> None:
        return

    async def send_warning(self, message: str) -> None:
        return

    async def send_critical(self, message: str) -> None:
        return


class TelegramAlerter:
    """Skeleton Telegram-alerter. **Не готов к live** — нужны bot token
    и chat_id, плюс httpx-вызов к Telegram Bot API.

    Использование (когда будет готов):

        alerter = TelegramAlerter(bot_token="...", chat_id="...")
        await alerter.send_critical("OrderRejected on BTC-USDT")

    Сейчас — `NoopAlerter` под капотом с warning, чтобы было заметно
    что Telegram не настроен. Полная реализация — отдельный план
    (требует Telegram Bot регистрации).
    """

    def __init__(self, bot_token: str | None = None, chat_id: str | None = None) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        if not bot_token or not chat_id:
            logger.warning("TelegramAlerter created without bot_token/chat_id — operating as noop")

    async def send(self, severity: Severity, message: str) -> None:
        if not self._bot_token or not self._chat_id:
            return
        # TODO: httpx POST к Telegram Bot API.
        # url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        # payload = {"chat_id": self._chat_id, "text": f"[{severity}] {message}"}
        # ... rate limiting, retry, etc.
        logger.warning("TelegramAlerter.send is not implemented yet")

    async def send_info(self, message: str) -> None:
        await self.send(Severity.INFO, message)

    async def send_warning(self, message: str) -> None:
        await self.send(Severity.WARNING, message)

    async def send_critical(self, message: str) -> None:
        await self.send(Severity.CRITICAL, message)
