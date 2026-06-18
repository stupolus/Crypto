"""Тесты Telegram-нотификатора без сетевых вызовов."""

from __future__ import annotations

import pytest

from paper.reporter import (
    NullReporter,
    TelegramReporter,
    build_reporter_from_env,
)


def test_null_reporter_returns_false() -> None:
    r = NullReporter()
    assert r.send("hi") is False


def test_telegram_serializes_and_sends() -> None:
    sent: list[tuple[str, bytes]] = []

    def fake_http(url: str, payload: bytes) -> int:
        sent.append((url, payload))
        return 200

    r = TelegramReporter(token="TKN", chat_id="42", http_sender=fake_http)
    assert r.send("hello") is True
    assert len(sent) == 1
    url, payload = sent[0]
    assert url == "https://api.telegram.org/botTKN/sendMessage"
    assert b'"chat_id": "42"' in payload
    assert b'"text": "hello"' in payload


def test_telegram_rate_limit_blocks_after_n() -> None:
    sent: list[bytes] = []
    clock = [1000.0]

    def fake_http(_url: str, payload: bytes) -> int:
        sent.append(payload)
        return 200

    r = TelegramReporter(
        token="TKN",
        chat_id="42",
        http_sender=fake_http,
        rate_limit_per_hour=3,
        clock=lambda: clock[0],
    )
    assert r.send("1") is True
    assert r.send("2") is True
    assert r.send("3") is True
    assert r.send("4") is False  # rate-limited
    # через час лимит сбрасывается
    clock[0] += 3601
    assert r.send("5") is True


def test_telegram_failed_http_returns_false() -> None:
    r = TelegramReporter(token="TKN", chat_id="42", http_sender=lambda u, p: 500)
    assert r.send("x") is False


def test_build_from_env_null_when_missing() -> None:
    r = build_reporter_from_env(env={})
    assert isinstance(r, NullReporter)


def test_build_from_env_telegram_when_present() -> None:
    r = build_reporter_from_env(env={"GOLDBOT_TG_TOKEN": "T", "GOLDBOT_TG_CHAT_ID": "C"})
    assert isinstance(r, TelegramReporter)


def test_token_chat_required() -> None:
    with pytest.raises(ValueError):
        TelegramReporter(token="", chat_id="C")
    with pytest.raises(ValueError):
        TelegramReporter(token="T", chat_id="")
