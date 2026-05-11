"""User Data Stream BingX (USDT-M perp), фаза 0.D part 2.

Что делает:
- Создаёт ``listenKey`` через `PrivateAPI.create_listen_key`.
- Подключается к ``wss://<base>/swap-market?listenKey=<KEY>``.
- Парсит push-события ``ORDER_TRADE_UPDATE`` / ``ACCOUNT_UPDATE`` в
  типизированные модели из ``private_models``.
- Фоновый task продлевает listenKey каждые ``keep_alive_interval_s`` (30 мин
  по умолчанию, при TTL 1 час — буфер 30 мин). Если PUT не удался —
  пересоздаём listenKey + reconnect.
- Прозрачный авто-реконнект с экспоненциальным backoff.

Принципиально отличается от ``BingXMarketWebSocket``: нет подписок на каналы
(квирк §7 п.17 plans/01: User Data Stream без subscribe — сервер сам шлёт все
типы событий по подключённому listenKey).
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import suppress
from types import TracebackType
from typing import Self

import websockets
from websockets.asyncio.client import ClientConnection

from adapters.bingx.config import BingXConfig
from adapters.bingx.exceptions import WebSocketError
from adapters.bingx.private import PrivateAPI
from adapters.bingx.private_models import (
    UserStreamEvent,
    UserStreamReconcileEvent,
    parse_user_stream_event,
)

logger = logging.getLogger(__name__)

ConnectFactory = Callable[[str], Awaitable[ClientConnection]]


async def _default_connect(url: str) -> ClientConnection:
    return await websockets.connect(
        url,
        ping_interval=None,
        ping_timeout=None,
        max_size=2**24,
    )


class BingXUserDataStream:
    """User-data WS-стрим с авто-keep-alive listenKey и reconnect.

    Использование::

        async with BingXUserDataStream(private_api) as stream:
            async for event in stream.events():
                ...
    """

    def __init__(
        self,
        private_api: PrivateAPI,
        config: BingXConfig | None = None,
        *,
        connect_factory: ConnectFactory | None = None,
    ) -> None:
        self._api = private_api
        self._cfg = config or private_api._config
        self._connect_factory = connect_factory or _default_connect

        self._listen_key: str | None = None
        self._conn: ClientConnection | None = None
        self._queue: asyncio.Queue[UserStreamEvent] = asyncio.Queue()
        self._session_task: asyncio.Task[None] | None = None
        self._keep_alive_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._connected_event = asyncio.Event()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    @property
    def listen_key(self) -> str | None:
        return self._listen_key

    async def __aenter__(self) -> Self:
        await self._open_listen_key()
        self._session_task = asyncio.create_task(
            self._session_loop(), name="bingx-user-stream-session"
        )
        self._keep_alive_task = asyncio.create_task(
            self._keep_alive_loop(), name="bingx-user-stream-keepalive"
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._stop_event.set()
        for t in (self._session_task, self._keep_alive_task):
            if t is not None and not t.done():
                t.cancel()
                with suppress(asyncio.CancelledError):
                    await t
        with suppress(Exception):
            if self._conn is not None:
                await self._conn.close()
        await self._close_listen_key_silently()

    async def events(self) -> AsyncIterator[UserStreamEvent]:
        """Async iterator с распарсенными событиями. Завершается при stop."""
        while True:
            if self._stop_event.is_set() and self._queue.empty():
                return
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            yield event

    # ── Internals ─────────────────────────────────────────────────────────

    async def _open_listen_key(self) -> None:
        key = await self._api.create_listen_key()
        self._listen_key = key
        logger.info("BingX listenKey acquired (%s...)", key[:8])

    async def _close_listen_key_silently(self) -> None:
        if not self._listen_key:
            return
        with suppress(Exception):
            await self._api.close_listen_key(self._listen_key)
        self._listen_key = None

    async def _session_loop(self) -> None:
        cfg = self._cfg.user_data_stream
        delay = cfg.reconnect_initial_delay_s
        while not self._stop_event.is_set():
            try:
                await self._run_session()
                delay = cfg.reconnect_initial_delay_s  # сброс после успеха
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("user-stream session error: %s; reconnect in %ss", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * cfg.reconnect_factor, cfg.reconnect_max_delay_s)

    async def _run_session(self) -> None:
        assert self._listen_key is not None
        ws_base = self._cfg.active_ws_market
        url = f"{ws_base}?listenKey={self._listen_key}"
        self._conn = await self._connect_factory(url)
        self._connected_event.set()
        # Reconcile: после (ре)коннекта эмитим снимок состояния через REST
        # ДО первых WS-событий. Стратегия инициализирует/синкает state.
        with suppress(Exception):
            await self._emit_reconcile()
        try:
            await self._read_loop()
        finally:
            self._connected_event.clear()
            conn = self._conn
            self._conn = None
            with suppress(Exception):
                if conn is not None:
                    await conn.close()

    async def _emit_reconcile(self) -> None:
        """REST-снимок balance + positions + open_orders → RECONCILE event."""
        import time as _time

        balances = await self._api.get_balance()
        positions = await self._api.get_positions()
        open_orders = await self._api.get_open_orders()
        event = UserStreamReconcileEvent(
            event_time_ms=int(_time.time() * 1000),
            balances=balances,
            positions=positions,
            open_orders=open_orders,
        )
        await self._queue.put(event)

    async def _read_loop(self) -> None:
        assert self._conn is not None
        cfg = self._cfg.user_data_stream
        async for frame in self._iter_frames(self._conn, cfg.watchdog_silence_s):
            if frame == "Ping":
                # BingX heartbeat (квирк §7 п.15) — отвечаем литералом.
                await self._conn.send("Pong")
                continue
            try:
                payload = json.loads(frame)
            except json.JSONDecodeError:
                logger.debug("user-stream: non-JSON frame ignored")
                continue
            if not isinstance(payload, dict):
                continue
            try:
                event = parse_user_stream_event(payload)
            except Exception as exc:
                logger.warning("user-stream: parse error %s for %r", exc, payload)
                continue
            if event is not None:
                await self._queue.put(event)

    @staticmethod
    async def _iter_frames(
        conn: ClientConnection, silence_s: float
    ) -> AsyncIterator[str]:
        """Декомпрессит gzip-фреймы, выдаёт текст. Watchdog по тишине."""
        while True:
            try:
                raw = await asyncio.wait_for(conn.recv(), timeout=silence_s)
            except TimeoutError as exc:
                raise WebSocketError(
                    f"user-stream watchdog timeout after {silence_s}s"
                ) from exc
            if isinstance(raw, bytes):
                try:
                    decoded = gzip.decompress(raw).decode("utf-8")
                except OSError:
                    # Может прийти и plain bytes — fallback.
                    decoded = raw.decode("utf-8", errors="replace")
            else:
                decoded = str(raw)
            yield decoded

    async def _keep_alive_loop(self) -> None:
        cfg = self._cfg.user_data_stream
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=cfg.keep_alive_interval_s,
                )
                # stop_event set — выходим
                return
            except TimeoutError:
                pass
            # Время продлевать.
            if not self._listen_key:
                continue
            try:
                await self._api.keep_alive_listen_key(self._listen_key)
                logger.debug("listenKey kept alive")
            except Exception as exc:
                logger.warning("listenKey keep-alive failed (%s); rotating key", exc)
                # Перевыпуск ключа + force-reconnect через session_task.
                with suppress(Exception):
                    await self._open_listen_key()
                if self._conn is not None:
                    with suppress(Exception):
                        await self._conn.close()
