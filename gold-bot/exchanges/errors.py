"""Нормализованные исключения адаптеров бирж.

ccxt бросает свой набор исключений; адаптеры конвертируют их в эти, чтобы
вышестоящий код (стратегии, runner'ы) не зависел напрямую от ccxt.
"""

from __future__ import annotations


class ExchangeError(Exception):
    """Базовое исключение адаптера биржи."""


class AuthError(ExchangeError):
    """Аутентификация: неверные/просроченные ключи, нет прав."""


class InsufficientFunds(ExchangeError):
    """Недостаточно средств для ордера."""


class InvalidOrder(ExchangeError):
    """Ордер отклонён биржей: размер, шаг цены, неизвестный символ и т.п."""


class RateLimitError(ExchangeError):
    """Превышен лимит запросов (HTTP 429 или биржевой код). Кандидат на backoff."""


class NetworkError(ExchangeError):
    """Сетевая ошибка / таймаут / 5xx. Кандидат на retry."""


class MarginModeError(ExchangeError):
    """Попытка использовать запрещённый режим маржи (cross)."""
