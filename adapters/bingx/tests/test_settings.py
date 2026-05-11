"""Unit-тесты ``adapters.bingx.settings``.

Что проверяется:
- Чтение ключей из переменных окружения по префиксу ``BINGX_``.
- Свойства ``active_key`` / ``active_secret`` переключаются по полю ``env``.
- ``has_credentials()`` отражает наличие обоих параметров.
- Лишние переменные среды (``BINGX_*``-чужие, не описанные в модели) игнорируются.

Реальный ``.env`` файл проекта не читаем: передаём ``_env_file=None`` —
это штатный механизм pydantic-settings для отключения чтения файла на инстансе.
"""

from __future__ import annotations

import pytest

from adapters.bingx.settings import BingXSettings


@pytest.fixture(autouse=True)
def _clean_bingx_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """На каждый тест чистим BINGX_* переменные окружения."""
    for var in (
        "BINGX_ENV",
        "BINGX_VST_API_KEY",
        "BINGX_VST_API_SECRET",
        "BINGX_LIVE_API_KEY",
        "BINGX_LIVE_API_SECRET",
    ):
        monkeypatch.delenv(var, raising=False)


def _make() -> BingXSettings:
    """Конструктор без чтения реального ``.env``."""
    return BingXSettings(_env_file=None)


def test_settings_default_env_is_vst() -> None:
    settings = _make()
    assert settings.env == "vst"
    assert settings.active_key is None
    assert settings.active_secret is None
    assert settings.has_credentials() is False


def test_settings_reads_vst_keys_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BINGX_VST_API_KEY", "vst-k")
    monkeypatch.setenv("BINGX_VST_API_SECRET", "vst-s")
    settings = _make()
    assert settings.active_key == "vst-k"
    assert settings.active_secret == "vst-s"
    assert settings.has_credentials() is True


def test_settings_active_keys_switch_with_env_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BINGX_ENV", "live")
    monkeypatch.setenv("BINGX_VST_API_KEY", "vst-k")
    monkeypatch.setenv("BINGX_VST_API_SECRET", "vst-s")
    monkeypatch.setenv("BINGX_LIVE_API_KEY", "live-k")
    monkeypatch.setenv("BINGX_LIVE_API_SECRET", "live-s")

    settings = _make()
    assert settings.env == "live"
    assert settings.active_key == "live-k"
    assert settings.active_secret == "live-s"


def test_settings_has_credentials_requires_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Только key или только secret — недостаточно."""
    monkeypatch.setenv("BINGX_VST_API_KEY", "vst-k")
    settings = _make()
    assert settings.has_credentials() is False


def test_settings_rejects_invalid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Значения env вне {vst, live} ловятся pydantic'ом."""
    monkeypatch.setenv("BINGX_ENV", "playground")
    with pytest.raises(ValueError):
        _make()


def test_settings_ignores_unknown_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Чужие BINGX_*-переменные не ломают парсинг (extra="ignore")."""
    monkeypatch.setenv("BINGX_FOO_BAR", "baz")
    monkeypatch.setenv("BINGX_VST_API_KEY", "k")
    monkeypatch.setenv("BINGX_VST_API_SECRET", "s")
    settings = _make()
    assert settings.active_key == "k"
