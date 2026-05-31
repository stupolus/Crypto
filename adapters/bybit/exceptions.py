"""Исключения адаптера Bybit.

По образцу `adapters/bingx/exceptions.py`: единые типы ошибок для всех
адаптеров проекта, чтобы стратегии не зависели от конкретной биржи.
"""

from __future__ import annotations


class BybitError(Exception):
    """Базовое исключение адаптера."""


class NetworkError(BybitError):
    """Транспортная ошибка (DNS, timeout, RST, 5xx после ретраев)."""


class AuthError(BybitError):
    """Подпись/ключ невалидны или истёк timestamp."""


class APIError(BybitError):
    """Bybit вернул `retCode != 0`. Содержит код+сообщение для решения."""

    def __init__(self, code: int, message: str, endpoint: str = "") -> None:
        self.code = code
        self.message = message
        self.endpoint = endpoint
        suffix = f" at {endpoint}" if endpoint else ""
        super().__init__(f"Bybit API error {code}{suffix}: {message}")


class RateLimited(APIError):
    """Server-side rate-limit Bybit V5. Retry-able.

    Известные коды:
    - 10006 — "Too many visits!" (per-UID/IP rate limit).
    - 10018 — IP rate limit / banned temporarily.
    - 10429 — request rate limited (новые версии).

    Транспортные 429 ловятся выше по статусу — это envelope-уровень.
    """
