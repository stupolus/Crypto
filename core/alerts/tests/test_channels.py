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


@pytest.mark.asyncio
async def test_telegram_alerter_sends_post_with_correct_payload(
    respx_mock: object,
) -> None:
    """Проверяем что POST уходит в правильный URL с правильным payload."""
    import httpx
    import respx

    mock: respx.Router = respx_mock  # type: ignore[assignment]
    route = mock.post("https://api.telegram.org/botTOKEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    async with httpx.AsyncClient() as client:
        alerter = TelegramAlerter(bot_token="TOKEN", chat_id="42", client=client)
        await alerter.send_critical("OrderRejected on BTC-USDT")

    assert route.called
    req = route.calls.last.request
    import json as _json

    body = _json.loads(req.content)
    assert body["chat_id"] == "42"
    assert "OrderRejected on BTC-USDT" in body["text"]
    assert "[CRITICAL]" in body["text"]


@pytest.mark.asyncio
async def test_telegram_alerter_swallows_http_errors(
    respx_mock: object, caplog: pytest.LogCaptureFixture
) -> None:
    """4xx/5xx не должны raises — alerter best-effort."""
    import httpx
    import respx

    mock: respx.Router = respx_mock  # type: ignore[assignment]
    mock.post("https://api.telegram.org/botTOKEN/sendMessage").mock(
        return_value=httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
    )
    async with httpx.AsyncClient() as client:
        alerter = TelegramAlerter(bot_token="TOKEN", chat_id="42", client=client)
        with caplog.at_level(logging.WARNING):
            await alerter.send_critical("test")  # не raises
    assert any("HTTP 401" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_telegram_alerter_swallows_network_errors(
    respx_mock: object, caplog: pytest.LogCaptureFixture
) -> None:
    """Network error не должен raises."""
    import httpx
    import respx

    mock: respx.Router = respx_mock  # type: ignore[assignment]
    mock.post("https://api.telegram.org/botTOKEN/sendMessage").mock(
        side_effect=httpx.ConnectError("boom")
    )
    async with httpx.AsyncClient() as client:
        alerter = TelegramAlerter(bot_token="TOKEN", chat_id="42", client=client)
        with caplog.at_level(logging.WARNING):
            await alerter.send_critical("test")  # не raises
    assert any("send failed" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_telegram_alerter_noop_when_no_credentials() -> None:
    """Без токена/chat_id — send не делает HTTP-вызов."""
    import httpx
    import respx

    with respx.mock(base_url="https://api.telegram.org", assert_all_called=False) as mock:
        route = mock.post("/botTOKEN/sendMessage")
        async with httpx.AsyncClient() as client:
            alerter = TelegramAlerter(bot_token=None, chat_id="42", client=client)
            await alerter.send_critical("ignored")
        assert not route.called


@pytest.mark.asyncio
async def test_stdout_alerter_includes_prefix(caplog: pytest.LogCaptureFixture) -> None:
    """StdoutAlerter с prefix='[X@Y]' должен добавлять его перед сообщением."""
    alerter = StdoutAlerter(prefix="[gold@XAU-USDT]")
    with caplog.at_level(logging.WARNING):
        await alerter.send_warning("place_order failed")
    assert any(
        "[gold@XAU-USDT]" in r.message and "place_order failed" in r.message for r in caplog.records
    )


@pytest.mark.asyncio
async def test_stdout_alerter_no_prefix_when_empty(caplog: pytest.LogCaptureFixture) -> None:
    """Без prefix сообщение идёт без custom-tag, только дефолтный ALERT."""
    alerter = StdoutAlerter()
    with caplog.at_level(logging.INFO):
        await alerter.send_info("starting")
    msg = next(r.message for r in caplog.records if "starting" in r.message)
    assert msg == "[ALERT] starting"


@pytest.mark.asyncio
async def test_telegram_alerter_includes_prefix() -> None:
    """TelegramAlerter с prefix вставляет его в payload text."""
    import httpx
    import respx

    with respx.mock(base_url="https://api.telegram.org") as mock:
        route = mock.post("/botTOKEN/sendMessage").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        async with httpx.AsyncClient() as client:
            alerter = TelegramAlerter(
                bot_token="TOKEN",
                chat_id="42",
                client=client,
                prefix="[llm@gold@XAU-USDT]",
            )
            await alerter.send_warning("place_order failed")
    assert route.called
    sent_payload = route.calls[0].request.read().decode()
    assert "[llm@gold@XAU-USDT]" in sent_payload
    assert "place_order failed" in sent_payload
