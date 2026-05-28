"""Тесты маскирования секретов и JSON-логирования."""

from __future__ import annotations

import io
import json
import logging

from exchanges.logging_utils import (
    JsonFormatter,
    SecretFilter,
    configure_logging,
    mask_secrets,
)

KEY = "AKIAFAKEKEY1234567890"
SECRET = "superSecretValue/with+chars=="


def test_mask_secrets_replaces_key() -> None:
    text = f"signing with apiKey={KEY}"
    out = mask_secrets(text, [KEY])
    assert KEY not in out
    assert "***" in out


def test_mask_secrets_multiple() -> None:
    text = f"key={KEY} secret={SECRET}"
    out = mask_secrets(text, [KEY, SECRET])
    assert KEY not in out
    assert SECRET not in out
    assert out.count("***") == 2


def test_mask_secrets_ignores_empty() -> None:
    text = "ничего секретного"
    out = mask_secrets(text, ["", KEY])
    assert out == text  # пустой секрет не затирает весь текст


def test_secret_filter_masks_record() -> None:
    record = logging.LogRecord(
        name="gold_bot",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request signed with %s",
        args=(KEY,),
        exc_info=None,
    )
    SecretFilter([KEY]).filter(record)
    assert KEY not in record.getMessage()
    assert "***" in record.getMessage()


def test_json_formatter_valid_json() -> None:
    record = logging.LogRecord(
        name="gold_bot",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    line = JsonFormatter().format(record)
    payload = json.loads(line)
    assert payload["level"] == "WARNING"
    assert payload["msg"] == "hello world"
    assert payload["logger"] == "gold_bot"


def test_configure_logging_masks_in_output() -> None:
    logger = configure_logging(level=logging.INFO, secrets=[KEY])
    buf = io.StringIO()
    # Перенаправляем единственный handler на буфер, сохранив форматтер и фильтр.
    handler = logger.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(buf)

    logger.info("calling api with key=%s", KEY)

    out = buf.getvalue()
    assert KEY not in out
    assert "***" in out
    payload = json.loads(out.strip())
    assert payload["level"] == "INFO"
