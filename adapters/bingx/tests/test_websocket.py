"""Unit-тесты WS-каркаса BingX.

Стратегия: подменяем фабрику коннекта (``connect_factory``) фейковым
``ClientConnection``-подобным объектом. Это позволяет покрыть критичные
ветки без живого сервера:
- gzip-разжатие входящего фрейма;
- ответ ``Pong`` на текстовый ``Ping`` (литералы, не JSON-payload);
- subscribe / ack / роутинг data-сообщений в очередь канала;
- декомпрессия → нечитаемое содержимое → WebSocketError;
- bytes-кадр vs str-кадр (на случай, если сервер шлёт оба).
"""

from __future__ import annotations

import asyncio
import gzip
import json
import uuid
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import pytest

from adapters.bingx.config import BingXConfig
from adapters.bingx.exceptions import WebSocketError
from adapters.bingx.websocket import BingXMarketWebSocket

# ── Fake ClientConnection ───────────────────────────────────────────────────


class _FakeConnection:
    """Минимальная имитация ``websockets.asyncio.client.ClientConnection``.

    - ``recv`` отдаёт следующий фрейм из ``incoming`` (deque). Если пусто —
      виснет (имитирует тишину; реальный тест должен это завершить через
      stop_event).
    - ``send`` складывает текст в ``sent``. Если на отправку зарегистрирована
      реакция в ``responders`` — она пушит ответ в ``incoming``.
    - ``close`` помечает соединение закрытым.
    """

    def __init__(self) -> None:
        self.incoming: deque[bytes | str] = deque()
        self.sent: list[str] = []
        self.responders: list[Callable[[str], Awaitable[None]]] = []
        self.closed = False
        self._data_event = asyncio.Event()

    async def recv(self) -> bytes | str:
        while not self.incoming and not self.closed:
            self._data_event.clear()
            await self._data_event.wait()
        if self.closed and not self.incoming:
            raise WebSocketError("fake conn closed")
        return self.incoming.popleft()

    async def send(self, data: str) -> None:
        self.sent.append(data)
        for responder in self.responders:
            await responder(data)

    async def close(self) -> None:
        self.closed = True
        self._data_event.set()

    def push(self, frame: bytes | str) -> None:
        self.incoming.append(frame)
        self._data_event.set()


def _gzip(payload: dict[str, Any] | str) -> bytes:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return gzip.compress(raw.encode("utf-8"))


# ── decode_frame: чистая функция ────────────────────────────────────────────


def test_decode_frame_unzips_bytes_and_returns_text() -> None:
    payload = {"a": 1, "b": "two"}
    raw = _gzip(payload)
    assert BingXMarketWebSocket._decode_frame(raw) == json.dumps(payload)


def test_decode_frame_passes_through_str_untouched() -> None:
    assert BingXMarketWebSocket._decode_frame("Ping") == "Ping"


def test_decode_frame_raises_on_broken_gzip() -> None:
    with pytest.raises(WebSocketError, match="gzip decode failure"):
        BingXMarketWebSocket._decode_frame(b"not-gzip-at-all")


# ── handle_text → маршрутизация ────────────────────────────────────────────


def test_handle_text_routes_data_message_to_channel_queue(cfg: BingXConfig) -> None:
    ws = BingXMarketWebSocket(cfg)
    queue: asyncio.Queue[Mapping[str, Any]] = asyncio.Queue()
    ws._channels["BTC-USDT@kline_1min"] = queue
    text = json.dumps({"dataType": "BTC-USDT@kline_1min", "data": {"close": "60500.7"}})
    ws._handle_text(text)
    assert queue.get_nowait() == {
        "dataType": "BTC-USDT@kline_1min",
        "data": {"close": "60500.7"},
    }


@pytest.mark.asyncio
async def test_handle_text_resolves_pending_ack_by_id(cfg: BingXConfig) -> None:
    ws = BingXMarketWebSocket(cfg)
    fut: asyncio.Future[Mapping[str, Any]] = asyncio.get_running_loop().create_future()
    msg_id = uuid.uuid4().hex
    ws._pending_ack[msg_id] = fut
    ws._handle_text(json.dumps({"id": msg_id, "code": 0, "msg": "SUCCESS"}))
    assert fut.done()
    assert fut.result() == {"id": msg_id, "code": 0, "msg": "SUCCESS"}


def test_handle_text_ignores_unknown_payload(cfg: BingXConfig) -> None:
    ws = BingXMarketWebSocket(cfg)
    # Не должен падать на чужих сообщениях; channels пуст, ack нет.
    ws._handle_text(json.dumps({"dataType": "ETH-USDT@kline_1min", "data": {}}))


# ── Полный цикл с FakeConnection ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_connect_and_pong_on_ping(cfg: BingXConfig) -> None:
    """При получении текстового ``Ping`` клиент должен ответить ``Pong``."""
    fake = _FakeConnection()
    fake.push("Ping")

    async def factory(url: str) -> _FakeConnection:
        return fake

    ws = BingXMarketWebSocket(cfg, connect_factory=factory)  # type: ignore[arg-type]
    await ws.connect()
    # Дать reader-loop успеть прочитать кадр и ответить.
    for _ in range(50):
        if "Pong" in fake.sent:
            break
        await asyncio.sleep(0.01)
    await ws.disconnect()
    assert "Pong" in fake.sent, f"expected Pong in {fake.sent!r}"


@pytest.mark.asyncio
async def test_subscribe_sends_correct_payload_and_routes_data(cfg: BingXConfig) -> None:
    fake = _FakeConnection()

    async def auto_ack(data: str) -> None:
        msg = json.loads(data)
        if msg.get("reqType") == "sub":
            ack = {"id": msg["id"], "code": 0, "msg": "SUCCESS", "timestamp": 0}
            fake.push(_gzip(ack))

    fake.responders.append(auto_ack)

    async def factory(url: str) -> _FakeConnection:
        return fake

    ws = BingXMarketWebSocket(cfg, connect_factory=factory)  # type: ignore[arg-type]
    await ws.connect()

    iterator = await ws.subscribe("BTC-USDT@kline_1min")

    # Проверим что sub-запрос был отправлен с правильным форматом.
    sub_payloads = [json.loads(s) for s in fake.sent if "sub" in s]
    assert sub_payloads, f"no sub payload in {fake.sent!r}"
    sub = sub_payloads[0]
    assert sub["reqType"] == "sub"
    assert sub["dataType"] == "BTC-USDT@kline_1min"
    assert "id" in sub

    # Запушим data-кадр и заберём через iterator.
    data_msg = {"dataType": "BTC-USDT@kline_1min", "data": {"c": "60500.7"}}
    fake.push(_gzip(data_msg))
    received = await asyncio.wait_for(iterator.__anext__(), timeout=2.0)
    assert received["dataType"] == "BTC-USDT@kline_1min"
    assert received["data"]["c"] == "60500.7"

    await ws.disconnect()


@pytest.mark.asyncio
async def test_subscribe_raises_when_ack_indicates_failure(cfg: BingXConfig) -> None:
    fake = _FakeConnection()

    async def deny_ack(data: str) -> None:
        msg = json.loads(data)
        if msg.get("reqType") == "sub":
            fake.push(_gzip({"id": msg["id"], "code": 80403, "msg": "too many topics"}))

    fake.responders.append(deny_ack)

    async def factory(url: str) -> _FakeConnection:
        return fake

    ws = BingXMarketWebSocket(cfg, connect_factory=factory)  # type: ignore[arg-type]
    await ws.connect()
    with pytest.raises(WebSocketError, match="subscribe to .* failed"):
        await ws.subscribe("BTC-USDT@kline_1min")
    await ws.disconnect()


@pytest.mark.asyncio
async def test_subscribe_before_connect_raises(cfg: BingXConfig) -> None:
    ws = BingXMarketWebSocket(cfg)
    with pytest.raises(WebSocketError, match="before connect"):
        await ws.subscribe("BTC-USDT@kline_1min")


@pytest.mark.asyncio
async def test_resubscribe_retries_on_transient_ack_timeout(
    cfg: BingXConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Регрессия на наблюдение D3 dry-run 2026-05-12: BingX иногда отдаёт
    ack-timeout на первый resubscribe после reconnect. Должны ретраить."""
    ws = BingXMarketWebSocket(cfg)
    ws._channels["BTC-USDT@kline_15m"] = asyncio.Queue()

    attempts: list[int] = []

    async def flaky_send(channel: str) -> None:
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise WebSocketError("ack timeout")
        # 3-я попытка — успех.

    # Замедляем backoff, чтобы тест не тянул секунды.
    monkeypatch.setattr("asyncio.sleep", _instant_sleep)
    monkeypatch.setattr(ws, "_send_subscribe", flaky_send)
    await ws._resubscribe_all()
    assert len(attempts) == 3, f"expected 3 attempts, got {attempts}"


@pytest.mark.asyncio
async def test_resubscribe_gives_up_after_3_attempts(
    cfg: BingXConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Если все 3 попытки фейлятся — НЕ raises, идёт к следующему каналу.
    Watchdog должен поднять полный reconnect если канал реально мёртвый."""
    ws = BingXMarketWebSocket(cfg)
    ws._channels["BTC-USDT@kline_15m"] = asyncio.Queue()
    ws._channels["ETH-USDT@kline_15m"] = asyncio.Queue()

    calls: list[str] = []

    async def always_fails(channel: str) -> None:
        calls.append(channel)
        raise WebSocketError("ack timeout")

    monkeypatch.setattr("asyncio.sleep", _instant_sleep)
    monkeypatch.setattr(ws, "_send_subscribe", always_fails)
    # Не raises — пробует оба канала.
    await ws._resubscribe_all()
    # 3 попытки × 2 канала.
    assert len(calls) == 6, f"expected 6 calls, got {calls}"


async def _instant_sleep(_: float) -> None:
    """Заглушка asyncio.sleep — мгновенно возвращает control."""
    return None
