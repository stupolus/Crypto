"""Синхронизация локальных часов с серверным временем BingX.

Зачем: BingX отвергает signed-запрос, если ``|timestamp - serverTime| > recvWindow``
(по умолчанию 5000 ms). На VPS/Mac часы могут плыть, особенно после suspend/resume.
Решение — держать ``offset_ms = serverTime - localMs`` и подставлять
``localMs + offset_ms`` в подпись.

Дизайн:
- Ленивая инициализация: первый ``now_ms()`` принудительно дергает ``sync()``,
  следующий — переиспользует cached offset, пока не прошёл ``interval_s``.
- Без фонового task'а на фазе 0.C. Фоновый resync — задел на 0.D вместе с
  user-data WS, где имеет смысл общий event-loop.
- ``sync()`` идёт через ``BingXClient.request_public`` ⇒ автоматически
  получает token-bucket и retry, как любой market-data запрос.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from adapters.bingx.exceptions import InvalidResponseError

if TYPE_CHECKING:
    from adapters.bingx.client import BingXClient


class ServerTimeSyncer:
    """Хранит offset между локальным monotonic clock и BingX server time.

    Использование::

        syncer = ServerTimeSyncer(client, server_time_path, interval_s=300)
        ts_ms = await syncer.now_ms()  # подставить в подпись
    """

    def __init__(
        self,
        client: BingXClient,
        server_time_path: str,
        interval_s: float,
    ) -> None:
        self._client = client
        self._path = server_time_path
        self._interval_s = interval_s
        self._offset_ms: int = 0
        self._last_sync_monotonic: float | None = None
        self._lock = asyncio.Lock()

    @property
    def offset_ms(self) -> int:
        return self._offset_ms

    @property
    def is_synced(self) -> bool:
        return self._last_sync_monotonic is not None

    async def sync(self) -> int:
        """Принудительно опросить ``/server/time`` и обновить offset.

        Возвращает новое значение offset в миллисекундах.
        """
        async with self._lock:
            data = await self._client.request_public("GET", self._path)
            if not isinstance(data, dict) or "serverTime" not in data:
                raise InvalidResponseError(
                    f"server time response missing 'serverTime': {data!r}"
                )
            server_ms = int(data["serverTime"])
            local_ms = int(time.time() * 1000)
            self._offset_ms = server_ms - local_ms
            self._last_sync_monotonic = time.monotonic()
            return self._offset_ms

    async def ensure_fresh(self) -> None:
        """Сделать sync, если ещё не делали или с прошлого прошло > interval_s."""
        if (
            self._last_sync_monotonic is None
            or (time.monotonic() - self._last_sync_monotonic) >= self._interval_s
        ):
            await self.sync()

    async def now_ms(self) -> int:
        """Текущее «серверное» время для подписи. Гарантирует fresh-sync."""
        await self.ensure_fresh()
        return int(time.time() * 1000) + self._offset_ms
