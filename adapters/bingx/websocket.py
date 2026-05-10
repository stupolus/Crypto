"""WebSocket-каркас для публичных market-стримов BingX (USDT-M perp).

Что делает:
- Подключается к ``wss://open-api-swap.bingx.com/swap-market`` (live) или
  VST-эквиваленту в зависимости от конфига.
- Декомпрессит каждый входящий фрейм (BingX шлёт всё в gzip — квирк §7 п.15).
- Отвечает текстовым ``Pong`` на текстовый ``Ping`` сервера (это литералы,
  не JSON-payload — квирк §7 п.15 plans/01).
- Watchdog: если за ``watchdog_silence_s`` ни данных, ни Ping — рвём
  сессию и реконнектимся.
- Прозрачный авто-реконнект с экспоненциальным backoff: ``connect()``
  стартует session loop, который переустанавливает коннект и
  переподписывается на все сохранённые каналы. Подписки потребителю
  не теряются.
- Async iterator API: ``async for msg in ws.subscribe("BTC-USDT@kline_1min"): ...``

Чего нет в фазе 0.B (отложено):
- Приватный user data stream (нужен listenKey, фаза 0.D).
- Адаптивный split на несколько коннектов при превышении 200 топиков.
- Метрики latency (фаза 0.E).
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import suppress
from types import TracebackType
from typing import Any, Self

import websockets
from websockets.asyncio.client import ClientConnection

from adapters.bingx.config import BingXConfig, get_default_config
from adapters.bingx.exceptions import WebSocketError

logger = logging.getLogger(__name__)


# Тип-алиас для DI: фабрика, открывающая ClientConnection. Позволяет тестам
# подменять реальный ``websockets.connect`` фейковым коннектом без сети.
ConnectFactory = Callable[[str], Awaitable[ClientConnection]]


async def _default_connect(url: str) -> ClientConnection:
    return await websockets.connect(
        url,
        # Отключаем библиотечный auto-pong — у BingX свой текстовый протокол.
        ping_interval=None,
        ping_timeout=None,
        max_size=2**24,  # 16 MiB — с запасом на gzip-кадры с большим payload.
    )


class BingXMarketWebSocket:
    """Один WS-коннект на public market data, с прозрачным реконнектом.

    Использование::

        async with BingXMarketWebSocket() as ws:
            async for msg in ws.subscribe("BTC-USDT@kline_1min"):
                print(msg)
    """

    def __init__(
        self,
        config: BingXConfig | None = None,
        *,
        connect_factory: ConnectFactory | None = None,
    ) -> None:
        self._cfg = config or get_default_config()
        self._url = self._cfg.active_ws_market
        self._connect_factory = connect_factory or _default_connect

        self._conn: ClientConnection | None = None
        # Каналы → очереди сообщений для потребителей.
        self._channels: dict[str, asyncio.Queue[Mapping[str, Any]]] = {}
        # Pending ack-фьючерсы: id запроса → future с ответом sub/unsub.
        self._pending_ack: dict[str, asyncio.Future[Mapping[str, Any]]] = {}
        self._session_task: asyncio.Task[None] | None = None
        self._connected_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        # 1024 кадра ≈ 17 минут 1m-свечей. Защита от runaway memory.
        self._channel_queue_size = 1024

    # ── Контекст-менеджер ──────────────────────────────────────────────────
    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.disconnect()

    # ── Жизненный цикл ─────────────────────────────────────────────────────
    async def connect(self) -> None:
        """Запустить session loop и дождаться первого успешного коннекта."""
        if self._session_task is not None and not self._session_task.done():
            return
        self._stop_event = asyncio.Event()
        self._connected_event = asyncio.Event()
        self._session_task = asyncio.create_task(self._session_loop(), name="bingx-ws-session")
        # Ждём, пока сессия установит первый коннект, либо сама упадёт.
        first_done = asyncio.create_task(self._connected_event.wait())
        done, _ = await asyncio.wait(
            [first_done, self._session_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        if self._session_task in done and not self._connected_event.is_set():
            # Session crashed before first connect — пробросим причину.
            await self._session_task
            raise WebSocketError("session failed to establish first connection")
        if not first_done.done():
            first_done.cancel()
            with suppress(asyncio.CancelledError):
                await first_done

    async def disconnect(self) -> None:
        """Корректно завершить сессию."""
        self._stop_event.set()
        if self._conn is not None:
            with suppress(Exception):
                await self._conn.close()
        if self._session_task is not None:
            with suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(self._session_task, timeout=2.0)
            self._session_task = None
        # Освобождаем зависшие ack-фьючерсы.
        for fut in self._pending_ack.values():
            if not fut.done():
                fut.set_exception(WebSocketError("disconnected"))
        self._pending_ack.clear()
        self._conn = None

    # ── Подписка ───────────────────────────────────────────────────────────
    async def subscribe(self, channel: str) -> AsyncIterator[Mapping[str, Any]]:
        """Подписаться на канал и получать сообщения как async iterator.

        Канал — строка ``<symbol>@<dataType>``, например
        ``BTC-USDT@kline_1min`` (квирк §7 п.12: WS-формат интервала).
        """
        if not self._connected_event.is_set():
            raise WebSocketError("subscribe called before connect()")

        if channel not in self._channels:
            queue: asyncio.Queue[Mapping[str, Any]] = asyncio.Queue(self._channel_queue_size)
            self._channels[channel] = queue
            await self._send_subscribe(channel)
        else:
            queue = self._channels[channel]

        return self._iter_channel(channel, queue)

    async def _iter_channel(
        self, channel: str, queue: asyncio.Queue[Mapping[str, Any]]
    ) -> AsyncIterator[Mapping[str, Any]]:
        try:
            while not self._stop_event.is_set():
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                except TimeoutError:
                    continue
                yield msg
        finally:
            self._channels.pop(channel, None)
            if self._conn is not None and not self._stop_event.is_set():
                with suppress(Exception):
                    await self._send_unsubscribe(channel)

    async def _send_subscribe(self, channel: str) -> None:
        ack = await self._send_with_ack({"reqType": "sub", "dataType": channel})
        if ack.get("code") != 0:
            raise WebSocketError(
                f"subscribe to {channel} failed: code={ack.get('code')} msg={ack.get('msg')}"
            )
        logger.info("BingX WS subscribed channel=%s", channel)

    async def _send_unsubscribe(self, channel: str) -> None:
        with suppress(Exception):
            await self._send_with_ack({"reqType": "unsub", "dataType": channel})

    async def _send_with_ack(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        if self._conn is None:
            raise WebSocketError("connection is not established")
        msg_id = uuid.uuid4().hex
        payload = {"id": msg_id, **body}
        future: asyncio.Future[Mapping[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending_ack[msg_id] = future
        try:
            await self._conn.send(json.dumps(payload))
            return await asyncio.wait_for(
                future, timeout=self._cfg.websocket.subscribe_ack_timeout_s
            )
        except TimeoutError as e:
            raise WebSocketError(f"ack timeout for id={msg_id} body={body}") from e
        finally:
            self._pending_ack.pop(msg_id, None)

    # ── Session loop с реконнектом ─────────────────────────────────────────
    async def _session_loop(self) -> None:
        """Держит активную сессию и переподнимает её при сбоях.

        Алгоритм:
        1. Открыть коннект.
        2. Если есть сохранённые каналы — переподписаться (после реконнекта).
        3. Сигналить ``connected_event`` (потребители могут вызывать subscribe).
        4. Читать кадры до ошибки/закрытия.
        5. На сбое: дождаться backoff и повторить, если не было ``stop``.
        """
        rc = self._cfg.websocket.reconnect
        delay = rc.initial_delay_s
        first = True
        while not self._stop_event.is_set():
            try:
                self._conn = await self._connect_factory(self._url)
                logger.info(
                    "BingX WS %s url=%s",
                    "connected" if first else "reconnected",
                    self._url,
                )
                # Переподписка на все сохранённые каналы (важно после reconnect).
                if not first:
                    await self._resubscribe_all()
                self._connected_event.set()
                # Успех → сбрасываем backoff.
                delay = rc.initial_delay_s
                first = False
                await self._reader_inner()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("BingX WS session ended: %s", e)
            finally:
                if self._conn is not None:
                    with suppress(Exception):
                        await self._conn.close()
                    self._conn = None
                # Активные ack-ожидания не переживут реконнект.
                for fut in self._pending_ack.values():
                    if not fut.done():
                        fut.set_exception(WebSocketError("connection lost"))
                self._pending_ack.clear()

            if self._stop_event.is_set():
                break
            await asyncio.sleep(delay)
            delay = min(delay * rc.factor, rc.max_delay_s)

    async def _resubscribe_all(self) -> None:
        for channel in list(self._channels):
            try:
                await self._send_subscribe(channel)
            except Exception as e:
                logger.warning("BingX WS resubscribe failed channel=%s: %s", channel, e)

    async def _reader_inner(self) -> None:
        if self._conn is None:
            return
        watchdog_s = self._cfg.websocket.watchdog_silence_s
        while not self._stop_event.is_set():
            try:
                raw = await asyncio.wait_for(self._conn.recv(), timeout=watchdog_s)
            except TimeoutError:
                raise WebSocketError(
                    f"silence over watchdog={watchdog_s}s — connection considered dead"
                ) from None
            except websockets.ConnectionClosed as e:
                rcvd = e.rcvd
                logger.info(
                    "BingX WS closed: code=%s reason=%s",
                    rcvd.code if rcvd is not None else None,
                    rcvd.reason if rcvd is not None else None,
                )
                return
            text = self._decode_frame(raw)
            if text == self._cfg.websocket.ping_text:
                await self._conn.send(self._cfg.websocket.pong_text)
                continue
            self._handle_text(text)

    @staticmethod
    def _decode_frame(raw: bytes | str) -> str:
        if isinstance(raw, bytes):
            try:
                return gzip.decompress(raw).decode("utf-8")
            except (OSError, UnicodeDecodeError) as e:
                raise WebSocketError(f"gzip decode failure: {e}") from e
        return raw

    def _handle_text(self, text: str) -> None:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("BingX WS non-JSON, non-Ping frame: %r", text[:200])
            return
        if not isinstance(payload, dict):
            logger.warning("BingX WS unexpected envelope: %r", text[:200])
            return
        # ack (sub/unsub): есть поле id.
        msg_id = payload.get("id")
        if msg_id is not None and msg_id in self._pending_ack:
            future = self._pending_ack[msg_id]
            if not future.done():
                future.set_result(payload)
            return
        # data: маршрутизируем по dataType.
        data_type = payload.get("dataType")
        if isinstance(data_type, str) and data_type in self._channels:
            queue = self._channels[data_type]
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning(
                    "BingX WS dropping message — channel queue full channel=%s", data_type
                )
            return
        logger.debug("BingX WS unrouted payload: %r", text[:200])
