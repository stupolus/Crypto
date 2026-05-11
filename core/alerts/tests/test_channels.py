"""Unit-тесты ``core.alerts``."""

from __future__ import annotations

import logging

import pytest

from core.alerts import (
    Alerter,
    NoopAlerter,
    Severity,
    StdoutAlerter,
    TelegramAlerter,
)


def test_protocol_compliance() -> None:
    assert isinstance(StdoutAlerter(), Alerter)
    assert isinstance(NoopAlerter(), Alerter)
    assert isinstance(TelegramAlerter(), Alerter)


@pytest.mark.asyncio
async def test_stdout_alerter_logs_at_correct_level(
    caplog: pytest.LogCaptureFixture,
) -> None:
    alerter = StdoutAlerter()
    with caplog.at_level(logging.DEBUG, logger="core.alerts.channels"):
        await alerter.send_info("hello info")
        await alerter.send_warning("hello warn")
        await alerter.send_critical("hello crit")

    levels = [rec.levelno for rec in caplog.records]
    assert logging.INFO in levels
    assert logging.WARNING in levels
    assert logging.CRITICAL in levels


@pytest.mark.asyncio
async def test_noop_alerter_does_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    alerter = NoopAlerter()
    with caplog.at_level(logging.DEBUG):
        await alerter.send_critical("important")
    # Никаких записей не должно быть от NoopAlerter.
    msgs = [r.message for r in caplog.records if "[ALERT]" in r.message]
    assert msgs == []


@pytest.mark.asyncio
async def test_telegram_alerter_warns_when_unconfigured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Без bot_token / chat_id — warning при создании."""
    with caplog.at_level(logging.WARNING):
        TelegramAlerter()
    assert any("operating as noop" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_severity_enum_values() -> None:
    assert Severity.INFO.value == "INFO"
    assert Severity.WARNING.value == "WARNING"
    assert Severity.CRITICAL.value == "CRITICAL"
