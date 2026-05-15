"""Unit-тесты ``build_fred_adapter_from_env``.

Проверяем что:
- При наличии ``FRED_API_KEY`` → строится FREDAdapter с HTTP-фетчером.
- При отсутствии → FREDFactoryError с понятным сообщением.
- ``client`` пробрасывается в фетчер.
"""

from __future__ import annotations

import httpx
import pytest

from parsers.macro.factory import FREDFactoryError, build_fred_adapter_from_env
from parsers.macro.fred_adapter import FREDAdapter
from parsers.macro.fred_http_fetcher import FREDHttpFetcher
from parsers.macro.settings import FREDSettings


def test_factory_builds_adapter_when_key_present() -> None:
    settings = FREDSettings(api_key="test-key-123")
    adapter = build_fred_adapter_from_env(settings=settings)
    assert isinstance(adapter, FREDAdapter)
    # Внутренний fetcher должен быть FREDHttpFetcher
    assert isinstance(adapter._fetcher, FREDHttpFetcher)


def test_factory_raises_when_key_missing() -> None:
    settings = FREDSettings(api_key=None)
    with pytest.raises(FREDFactoryError, match="FRED_API_KEY"):
        build_fred_adapter_from_env(settings=settings)


def test_factory_raises_when_key_empty() -> None:
    settings = FREDSettings(api_key="")
    with pytest.raises(FREDFactoryError, match="FRED_API_KEY"):
        build_fred_adapter_from_env(settings=settings)


def test_factory_passes_client_to_fetcher() -> None:
    settings = FREDSettings(api_key="test-key")
    with httpx.Client() as client:
        adapter = build_fred_adapter_from_env(settings=settings, client=client)
    fetcher = adapter._fetcher
    assert isinstance(fetcher, FREDHttpFetcher)
    assert fetcher._client is client
    assert fetcher._owns_client is False


def test_factory_default_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без явных settings — читается из env (FRED_API_KEY)."""
    monkeypatch.setenv("FRED_API_KEY", "env-key-456")
    adapter = build_fred_adapter_from_env()
    assert isinstance(adapter, FREDAdapter)
    fetcher = adapter._fetcher
    assert isinstance(fetcher, FREDHttpFetcher)
    assert fetcher._api_key == "env-key-456"


def test_factory_default_settings_raises_when_env_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    # Если в репо лежит .env с FRED_API_KEY — этот тест может ложно проходить.
    # В CI .env отсутствует, поэтому проверка валидна.
    # Локально пропускаем если ключ всё же подгрузился.
    settings = FREDSettings()
    if settings.configured:
        pytest.skip("FRED_API_KEY присутствует в .env — пропускаем negative test")
    with pytest.raises(FREDFactoryError):
        build_fred_adapter_from_env()
