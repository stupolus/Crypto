"""Unit-тесты BingXSettings: парсинг env vars, обработка отсутствующих ключей."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from adapters.bingx.exceptions import ConfigError
from adapters.bingx.settings import BingXSettings

_BINGX_ENV_NAMES = (
    "BINGX_VST_API_KEY",
    "BINGX_VST_API_SECRET",
    "BINGX_LIVE_API_KEY",
    "BINGX_LIVE_API_SECRET",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    """Стерильное окружение: убираем все BINGX_* env vars и .env-файл.

    Pydantic-settings ищет ``.env`` относительно cwd, поэтому переключаем
    cwd на пустой ``tmp_path``, чтобы не подцепить настоящий .env репозитория.
    """
    for name in _BINGX_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def _make_settings(**env: str) -> BingXSettings:
    """Утилита: создать настройки прямо из аргументов, минуя env+файл."""
    return BingXSettings(**env)  # type: ignore[arg-type]


def test_settings_loads_vst_keys_from_env(monkeypatch: pytest.MonkeyPatch, clean_env: Path) -> None:
    monkeypatch.setenv("BINGX_VST_API_KEY", "vst-key-123")
    monkeypatch.setenv("BINGX_VST_API_SECRET", "vst-secret-456")
    s = BingXSettings()
    key, secret = s.credentials_for("vst")
    assert key == "vst-key-123"
    assert secret == "vst-secret-456"


def test_settings_loads_from_dotenv_file(clean_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (clean_env / ".env").write_text(
        "BINGX_VST_API_KEY=key-from-file\nBINGX_VST_API_SECRET=secret-from-file\n",
        encoding="utf-8",
    )
    s = BingXSettings()
    key, secret = s.credentials_for("vst")
    assert key == "key-from-file"
    assert secret == "secret-from-file"


def test_settings_secret_value_is_masked_in_repr() -> None:
    """SecretStr должен скрывать значение в repr — наш барьер против логов."""
    s = _make_settings(BINGX_VST_API_KEY="secret-key", BINGX_VST_API_SECRET="secret-secret")
    rendered = repr(s)
    assert "secret-key" not in rendered
    assert "secret-secret" not in rendered
    assert "SecretStr" in rendered or "**********" in rendered


def test_credentials_for_unknown_env_raises_config_error() -> None:
    s = _make_settings()
    with pytest.raises(ConfigError, match="unsupported env"):
        s.credentials_for("paper")


def test_credentials_for_missing_pair_raises_config_error(clean_env: Path) -> None:
    s = BingXSettings()  # пусто
    with pytest.raises(ConfigError, match="missing"):
        s.credentials_for("vst")


def test_credentials_for_half_pair_raises_config_error() -> None:
    s = _make_settings(BINGX_VST_API_KEY="key-only")
    with pytest.raises(ConfigError, match="missing"):
        s.credentials_for("vst")


def test_has_credentials_for_returns_correct_flag(clean_env: Path) -> None:
    assert BingXSettings().has_credentials_for("vst") is False
    s = _make_settings(BINGX_VST_API_KEY="k", BINGX_VST_API_SECRET="s")
    assert s.has_credentials_for("vst") is True
    assert s.has_credentials_for("live") is False


def test_settings_ignores_extra_env_vars(
    monkeypatch: pytest.MonkeyPatch, clean_env: Path, capsys: pytest.CaptureFixture[Any]
) -> None:
    """Сторонние BINGX_*-переменные не должны валидно загружаться (alias-only)."""
    monkeypatch.setenv("BINGX_FOO", "bar")  # неизвестное поле
    s = BingXSettings()
    assert s.has_credentials_for("vst") is False
    # Самопроверка отсутствия лишних атрибутов.
    assert not hasattr(s, "BINGX_FOO")
    assert not os.environ.get("BINGX_VST_API_KEY")
