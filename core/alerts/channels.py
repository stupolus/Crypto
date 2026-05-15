"""Notification channels: stdout (default) + Telegram (HTTP).

Generic интерфейс для алертов о критичных событиях. Стратегия / runner
зовут `alerter.send_critical(msg)` — фактический канал доставки
подменяется через DI.

- `StdoutAlerter` — печать в logging с уровнем INFO/WARNING/CRITICAL.
- `NoopAlerter` — полная заглушка (для тестов).
- `TelegramAlerter` — POST к Bot API. Best-effort: ошибки сети
  логируются, но не пробрасываются (алерт не должен валить runner).
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Protocol, runtime_checkable

import httpx

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

    ``prefix`` — instance-tag (например, ``"[btc_breakout@BTC-USDT]"``),
    добавляется к каждому сообщению. Полезно когда несколько runner'ов
    пишут в один лог/чат.
    """

    def __init__(self, prefix: str = "") -> None:
        self._prefix = prefix

    async def send(self, severity: Severity, message: str) -> None:
        level = {
            Severity.INFO: logging.INFO,
            Severity.WARNING: logging.WARNING,
            Severity.CRITICAL: logging.CRITICAL,
        }[severity]
        tagged = f"{self._prefix} {message}" if self._prefix else message
        logger.log(level, "[ALERT] %s", tagged)

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


_TELEGRAM_BOT_API = "https://api.telegram.org"
_TELEGRAM_TIMEOUT_S = 5.0
_SEVERITY_EMOJI = {
    Severity.INFO: "ℹ️",
    Severity.WARNING: "⚠️",
    Severity.CRITICAL: "🚨",
}


class TelegramAlerter:
    """Алерт через Telegram Bot API (sendMessage).

    Best-effort: при ошибках сети / 4xx / 5xx логирует WARNING и
    возвращает — НЕ raises (алерт не должен валить runner).

    Параметры:
    - ``bot_token`` / ``chat_id`` — из @BotFather и chat (get через
      getUpdates). Если хоть один пустой — alerter работает как noop
      с warning при создании.
    - ``client`` — опциональный ``httpx.AsyncClient`` (для тестов).
      По умолчанию создаётся свой с таймаутом 5s.

    См. ``docs/telegram-setup.md`` для пошаговой настройки.
    """

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        prefix: str = "",
    ) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=_TELEGRAM_TIMEOUT_S)
        self._prefix = prefix
        if not bot_token or not chat_id:
            logger.warning("TelegramAlerter created without bot_token/chat_id — operating as noop")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def send(self, severity: Severity, message: str) -> None:
        if not self._bot_token or not self._chat_id:
            return
        emoji = _SEVERITY_EMOJI[severity]
        tagged = f"{self._prefix} {message}" if self._prefix else message
        text = f"{emoji} [{severity.value}] {tagged}"
        url = f"{_TELEGRAM_BOT_API}/bot{self._bot_token}/sendMessage"
        payload = {"chat_id": self._chat_id, "text": text}
        try:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            # 400/401 — конфиг битый (не той chat_id / просрочен токен).
            # Не спамим логом каждый алерт; пишем как WARNING один раз.
            logger.warning(
                "TelegramAlerter HTTP %s: %s",
                e.response.status_code,
                e.response.text[:200],
            )
        except Exception as e:
            logger.warning("TelegramAlerter send failed: %s", e)

    async def send_info(self, message: str) -> None:
        await self.send(Severity.INFO, message)

    async def send_warning(self, message: str) -> None:
        await self.send(Severity.WARNING, message)

    async def send_critical(self, message: str) -> None:
        await self.send(Severity.CRITICAL, message)
