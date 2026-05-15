"""Factory-функции для macro-адаптеров — собирают адаптер из env.

Вынесено отдельно от ``fred_adapter.py`` чтобы FREDAdapter (чистая логика)
не зависел от ``pydantic_settings`` и ``httpx`` — это нужно только если
вы строите production-инстанс из переменных окружения.
"""

from __future__ import annotations

import logging

import httpx

from parsers.macro.fred_adapter import FREDAdapter
from parsers.macro.fred_http_fetcher import FREDHttpFetcher
from parsers.macro.settings import FREDSettings

logger = logging.getLogger(__name__)


class FREDFactoryError(RuntimeError):
    """FRED_API_KEY не найден в env — нельзя построить production-адаптер."""


def build_fred_adapter_from_env(
    *,
    settings: FREDSettings | None = None,
    client: httpx.Client | None = None,
) -> FREDAdapter:
    """Собрать ``FREDAdapter`` с реальным HTTP-фетчером из переменных окружения.

    Если ``FRED_API_KEY`` отсутствует — ``FREDFactoryError``. Caller сам решает:
    падать или строить ``FREDAdapter`` со stub-фетчером (для тестов / dev).

    ``client`` — опциональный shared httpx.Client (например, чтобы делить
    connection pool с другими адаптерами). Если не передан — фетчер создаст
    свой и закроет в ``close()``.
    """
    settings = settings or FREDSettings()
    if not settings.configured:
        raise FREDFactoryError(
            "FRED_API_KEY не найден в окружении — пропиши в .env или передай "
            "fetcher вручную через FREDAdapter(fetcher=...)"
        )
    # mypy: settings.configured уже гарантирует api_key is not None
    assert settings.api_key is not None
    fetcher = FREDHttpFetcher(api_key=settings.api_key, client=client)
    logger.info("FREDAdapter собран с HTTP-фетчером (api_key=***%s)", settings.api_key[-4:])
    return FREDAdapter(fetcher=fetcher)
