"""Unit-тесты ``core.alerts.settings.TelegramSettings``."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.alerts.settings import TelegramSettings


def test_unconfigured_when_no_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Без переменных окружения и без .env — не сконфигурирован."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    # Подменим путь к .env на пустой, чтобы pydantic-settings не нашёл реальный.
    fake_env = tmp_path / "empty.env"
    fake_env.touch()
    s = TelegramSettings(_env_file=str(fake_env))
    assert not s.configured


def test_configured_when_both_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    fake_env = tmp_path / "empty.env"
    fake_env.touch()
    s = TelegramSettings(_env_file=str(fake_env))
    assert s.configured
    assert s.bot_token == "1234:abc"
    assert s.chat_id == "42"


def test_not_configured_when_only_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234:abc")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    fake_env = tmp_path / "empty.env"
    fake_env.touch()
    s = TelegramSettings(_env_file=str(fake_env))
    assert not s.configured


def test_reads_from_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Главный кейс: значения берутся из .env когда нет в окружении."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    env = tmp_path / "test.env"
    env.write_text("TELEGRAM_BOT_TOKEN=fromfile:xyz\nTELEGRAM_CHAT_ID=99\n")
    s = TelegramSettings(_env_file=str(env))
    assert s.configured
    assert s.bot_token == "fromfile:xyz"
    assert s.chat_id == "99"
