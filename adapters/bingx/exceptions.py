"""Иерархия исключений BingX-адаптера.

Источник: plans/01-bingx-адаптер.md §6 «Обработка ошибок и retry-стратегия».
Кодировано так, что вызывающий слой (стратегия / risk engine) различает:
- сетевые/временные сбои (можно ретраить),
- лимит/блокировку (бэкофф по Retry-After),
- ошибки авторизации (kill switch),
- ошибки бизнес-логики ордера (не ретраить, поднять алерт).
"""

from __future__ import annotations


class BingXError(Exception):
    """Базовый тип всех ошибок адаптера."""


class NetworkError(BingXError):
    """Транспортная ошибка: timeout, DNS, conn reset.

    Идемпотентные операции — ретраим. Неидемпотентные — поднимаем выше.
    """


class RateLimited(BingXError):
    """HTTP 429 либо бизнес-код перегрузки.

    Сервер обычно блокирует ключ на ~5 минут (docs-v3 → Frequency Limit).
    Адаптер уважает заголовок ``Retry-After``/``X-RateLimit-Requests-Expire``
    или экспоненциальный backoff.
    """

    def __init__(self, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class AuthError(BingXError):
    """401/403 от BingX. Не ретраим; поднимаем kill switch и Telegram-алерт."""


class ServerError(BingXError):
    """5xx от BingX. Ретраим с лимитом попыток."""


class APIError(BingXError):
    """Бизнес-ошибка от BingX: HTTP 200, но ``code != 0``.

    BingX отвечает 200 OK даже на отказы; статус операции в JSON-теле
    (``code``, ``msg``). Источник: docs-v3 → Quick Start → Error Code.
    """

    def __init__(self, code: int, message: str, *, endpoint: str | None = None) -> None:
        super().__init__(f"BingX API error {code} at {endpoint}: {message}")
        self.code = code
        self.message = message
        self.endpoint = endpoint


class InvalidResponseError(BingXError):
    """Ответ не разобрался pydantic-моделью или пустой.

    Сигнализирует о расхождении между нашей моделью и фактическим API
    (BingX иногда меняет схемы без анонса — см. plans/01 §10 п.1).
    """


class WebSocketError(BingXError):
    """Ошибка WS-слоя: разрыв, неудачный subscribe, gzip-decode failure."""


class ConfigError(BingXError):
    """Ошибка загрузки/валидации config.yaml."""


class OrderRejected(BingXError):
    """Ордер размещён, но пост-условие не выполнено.

    Основной случай — compensating-close: `place_order` получил ack, но
    связанный SL не появился в `get_open_orders` за заданное время. Адаптер
    автоматически закрывает позицию рыночным reduce_only и поднимает это
    исключение — стратегия должна расценивать как «вход не состоялся».

    Не ретраим: причина бизнес-логики, а не транспорта.
    """
