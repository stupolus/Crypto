"""Telegram-нотификатор для paper-runner'а.

Опционален: если переменные окружения GOLDBOT_TG_TOKEN / GOLDBOT_TG_CHAT_ID
не заданы — модуль превращается в no-op (NullReporter), runner идёт в лог.

Использует stdlib `urllib.request`, чтобы не тащить httpx/aiohttp в основные
зависимости. На синхронной HTTP-ноге проще тестировать. Сетевой вызов
делается через инжектируемый sender — тесты подменяют его и проверяют
сериализацию, не дёргая сеть.

Безопасность: токен не печатается в лог. В коде нет f-строк, выводящих
self._token. Если будущий рефакторинг попробует — SecretFilter из
exchanges.logging_utils замаскирует, но лучше не полагаться.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Protocol

_API_BASE = "https://api.telegram.org/bot"
_TIMEOUT_SECONDS = 10
_DEFAULT_RATE_LIMIT = 30  # сообщений в час, защитный потолок


class Reporter(Protocol):
    def send(self, text: str) -> bool: ...


class NullReporter:
    """No-op: если Telegram не настроен — runner всё равно работает."""

    def send(self, text: str) -> bool:
        return False


HttpSender = Callable[[str, bytes], int]
"""HTTP-отправитель: (url, json_payload_bytes) -> http_status."""


def _default_http_sender(url: str, payload: bytes) -> int:
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as e:
        return int(e.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0  # сеть упала — это не повод ронять paper-runner


class TelegramReporter:
    """Шлёт сообщение в Telegram-чат, с защитой от rate-limit."""

    def __init__(
        self,
        token: str,
        chat_id: str,
        http_sender: HttpSender = _default_http_sender,
        rate_limit_per_hour: int = _DEFAULT_RATE_LIMIT,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if not token or not chat_id:
            raise ValueError("token и chat_id обязательны для TelegramReporter")
        self._token = token
        self._chat_id = chat_id
        self._http = http_sender
        self._limit = rate_limit_per_hour
        from time import time as default_clock

        self._clock = clock or default_clock
        self._sent_timestamps: list[float] = []

    def _rate_limited(self) -> bool:
        now = self._clock()
        cutoff = now - 3600.0
        self._sent_timestamps = [t for t in self._sent_timestamps if t >= cutoff]
        return len(self._sent_timestamps) >= self._limit

    def send(self, text: str) -> bool:
        if self._rate_limited():
            return False
        url = _API_BASE + self._token + "/sendMessage"
        payload = json.dumps(
            {"chat_id": self._chat_id, "text": text, "disable_notification": False}
        ).encode("utf-8")
        status = self._http(url, payload)
        ok = 200 <= status < 300
        if ok:
            self._sent_timestamps.append(self._clock())
        return ok


def build_reporter_from_env(env: dict[str, str] | None = None) -> Reporter:
    """Вернёт TelegramReporter если оба env заданы, иначе NullReporter."""
    src = env if env is not None else dict(os.environ)
    token = src.get("GOLDBOT_TG_TOKEN", "")
    chat = src.get("GOLDBOT_TG_CHAT_ID", "")
    if not token or not chat:
        return NullReporter()
    return TelegramReporter(token=token, chat_id=chat)
