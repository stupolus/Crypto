"""Async HTTP-клиент BingX.

Слой ниже ``public.py``: знает про подпись, rate limit, retry, разбор
бизнес-ошибок ``code != 0``. Сами эндпоинты и pydantic-парсинг — наверху.

Дизайн-решения:
- ``httpx.AsyncClient`` (поддержка HTTP/1.1, async, моки через respx).
- Token bucket для глобального market data лимита (350/10s по конфигу,
  что 70% от официальных 500/10s — буфер на всплески, см. plans/01 §10 п.5).
- Retry-policy: только идемпотентные методы (GET/PUT/DELETE) + ретраимые
  HTTP-статусы из конфига (429, 5xx). POST не ретраим автоматически —
  идемпотентность управляется через ``client_order_id`` в фазе 0.D.
- HMAC-подпись: реализована, но в фазе 0.B недостижима — все вызовы идут
  через ``request_public``. ``request_signed`` гейтится наличием ключей
  в ``BingXClient``; без них бросает ``AuthError``.

Источник всех квирков и форматов: docs-v3 → Quick Start → Signature Authentication.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

import httpx

from adapters.bingx.config import BingXConfig, get_default_config
from adapters.bingx.exceptions import (
    APIError,
    AuthError,
    InvalidResponseError,
    NetworkError,
    RateLimited,
    ServerError,
)


@dataclass
class _TokenBucket:
    """Скользящее окно: ``capacity`` запросов за ``window_s`` секунд.

    Не классический token-bucket с пополнением, а sliding window —
    точнее отражает «N запросов за окно W», как сформулировано в docs-v3.
    """

    capacity: int
    window_s: float
    _stamps: deque[float] = field(default_factory=deque)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def acquire(self) -> None:
        """Заблокировать вызов, пока есть свободный слот в окне."""
        while True:
            async with self._lock:
                now = time.monotonic()
                cutoff = now - self.window_s
                while self._stamps and self._stamps[0] <= cutoff:
                    self._stamps.popleft()
                if len(self._stamps) < self.capacity:
                    self._stamps.append(now)
                    return
                # Самая старая метка задаёт момент, когда освободится слот.
                wait_s = self._stamps[0] + self.window_s - now
            await asyncio.sleep(max(wait_s, 0.001))


def sign_query(params: Mapping[str, Any], secret: str) -> str:
    """HMAC-SHA256 подпись BingX.

    Алгоритм (docs-v3 → Quick Start → Signature Authentication):

    1. Все параметры (бизнес + ``timestamp``) сортируются по ASCII
       по имени ключа.
    2. Собирается строка ``key1=v1&key2=v2&...&timestamp=ms``
       **без URL-encoding**.
    3. HMAC-SHA256(secret, message) → 64-символьный lowercase hex.

    URL-encoding делается отдельно при сборке итогового URL запроса.
    """
    canonical = "&".join(f"{k}={params[k]}" for k in sorted(params))
    digest = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


class BingXClient:
    """Базовый HTTP-клиент.

    Использование::

        async with BingXClient() as client:
            data = await client.request_public("GET", "/openApi/swap/v2/server/time")

    Ключи (api_key/api_secret) опциональны — без них доступен только
    публичный API. В фазе 0.B запускается без ключей.
    """

    def __init__(
        self,
        config: BingXConfig | None = None,
        *,
        api_key: str | None = None,
        api_secret: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config or get_default_config()
        self._api_key = api_key
        self._api_secret = api_secret
        timeout = httpx.Timeout(
            self._config.http.total_timeout_s,
            connect=self._config.http.connect_timeout_s,
            read=self._config.http.read_timeout_s,
        )
        self._http = httpx.AsyncClient(
            base_url=self._config.active_rest_base,
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": "crypto-bingx-adapter/0.0.1"},
        )
        bucket_cfg = self._config.rate_limits.market_data
        self._market_bucket = _TokenBucket(
            capacity=bucket_cfg.capacity, window_s=bucket_cfg.window_s
        )
        # ── server-time offset ──
        # ``request_signed`` использует ``serverTime + offset_ms`` как timestamp.
        # Без синка offset=0, что означает «верь локальным часам» — допустимо
        # на машинах с NTP, но мы делаем синк перед первым подписанным вызовом
        # и потом не чаще чем раз в ``server_time_resync_interval_s``.
        self._server_time_offset_ms: int = 0
        # ``time.monotonic()`` момента последней синхронизации.
        # ``None`` = ни разу не синхронизировались.
        self._last_server_time_sync: float | None = None
        # Лок предотвращает гонку при одновременных приватных вызовах:
        # только один таск делает запрос server/time.
        self._server_time_lock = asyncio.Lock()

    # ── Контекст-менеджер ──────────────────────────────────────────────────
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ── Публичный API ──────────────────────────────────────────────────────
    async def request_public(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Публичный (неподписанный) запрос. Возвращает поле ``data`` ответа.

        Поднимает соответствующее исключение из ``adapters.bingx.exceptions``.
        """
        await self._market_bucket.acquire()
        return await self._send_with_retry(method, path, params=params)

    async def request_signed(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        """Приватный (подписанный) запрос с HMAC-SHA256.

        Алгоритм (квирк §7 п.18 plans/01):
        1. Если синк часов протух (или ни разу не делался) — запрашиваем
           ``GET /server/time``, обновляем offset.
        2. К пользовательским ``params`` добавляем ``timestamp = now_ms + offset``
           и ``recvWindow``. Подпись считается по этим параметрам, ASCII-сортированным,
           без URL-encoding.
        3. ``signature`` добавляется к параметрам **после** расчёта подписи.
        4. Header ``X-BX-APIKEY: <api_key>``.

        Поднимает ``AuthError`` если ключи не заданы (фаза 0.C+ обязательны).
        """
        if not self._api_key or not self._api_secret:
            raise AuthError(
                "request_signed requires api_key/api_secret; "
                "BingXClient created in public-only mode"
            )
        await self._ensure_server_time_synced()
        merged: dict[str, Any] = dict(params or {})
        merged["timestamp"] = self.now_ms()
        merged["recvWindow"] = self._config.signing.recv_window_ms
        merged["signature"] = sign_query(merged, self._api_secret)
        await self._market_bucket.acquire()
        headers = {self._config.signing.api_key_header: self._api_key}
        return await self._send_with_retry(method, path, params=merged, headers=headers)

    # ── Серверное время / синхронизация ────────────────────────────────────
    def now_ms(self) -> int:
        """Локальное время в мс с поправкой на разницу с биржей.

        В подписи BingX требует, чтобы ``|timestamp - serverTime| <= recvWindow``
        (квирк §7 п.19 plans/01, default 5 с). На машинах с дрейфом NTP без
        offset может реджектить ``code=109414 "expired"``.
        """
        return int(time.time() * 1000) + self._server_time_offset_ms

    async def sync_server_time(self) -> int:
        """Принудительный синк часов с BingX.

        Дёргает ``GET /server/time``, считает разницу между сервером
        и локальным временем, сохраняет в ``_server_time_offset_ms``.

        Возвращает новый offset в мс (>0 — биржа впереди, <0 — позади).
        """
        async with self._server_time_lock:
            local_before = int(time.time() * 1000)
            payload = await self._send_with_retry(
                "GET", self._config.rest_endpoints.server_time
            )
            local_after = int(time.time() * 1000)
            if not isinstance(payload, Mapping) or "serverTime" not in payload:
                raise InvalidResponseError(
                    f"server/time payload missing 'serverTime': {payload!r}"
                )
            server_ms = int(payload["serverTime"])
            # Поправка на RTT: считаем, что биржа отдала свой serverTime
            # в середине окна (грубое допущение, но достаточно для 5-сек recvWindow).
            local_mid = (local_before + local_after) // 2
            self._server_time_offset_ms = server_ms - local_mid
            self._last_server_time_sync = time.monotonic()
            return self._server_time_offset_ms

    async def _ensure_server_time_synced(self) -> None:
        """Re-sync если прошло > ``server_time_resync_interval_s`` с прошлого."""
        interval = self._config.signing.server_time_resync_interval_s
        last = self._last_server_time_sync
        if last is None or (time.monotonic() - last) >= interval:
            await self.sync_server_time()

    # ── Внутренности ───────────────────────────────────────────────────────
    async def _send_with_retry(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        retry_cfg = self._config.http.retry
        last_exc: Exception | None = None
        delay = retry_cfg.backoff_initial_s
        for attempt in range(1, retry_cfg.max_attempts + 1):
            try:
                response = await self._http.request(
                    method,
                    path,
                    params=dict(params) if params else None,
                    headers=dict(headers) if headers else None,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = NetworkError(f"transport error on {method} {path}: {exc}")
                if attempt >= retry_cfg.max_attempts:
                    break
                await asyncio.sleep(delay)
                delay = min(delay * retry_cfg.backoff_factor, retry_cfg.backoff_max_s)
                continue

            status = response.status_code
            if status == 401 or status == 403:
                raise AuthError(f"BingX auth failed: HTTP {status} {response.text[:200]}")
            if status in retry_cfg.retryable_statuses:
                retry_after = self._parse_retry_after(response)
                if status == 429:
                    last_exc = RateLimited(
                        f"rate-limited HTTP 429 at {path}", retry_after_s=retry_after
                    )
                else:
                    last_exc = ServerError(f"BingX server error HTTP {status} at {path}")
                if attempt >= retry_cfg.max_attempts:
                    break
                await asyncio.sleep(retry_after if retry_after is not None else delay)
                delay = min(delay * retry_cfg.backoff_factor, retry_cfg.backoff_max_s)
                continue
            if status >= 400:
                raise APIError(status, response.text[:200], endpoint=path)
            return self._unwrap_payload(response, path)

        assert last_exc is not None  # цикл прошёл retry без успеха
        raise last_exc

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        # BingX отдаёт ``X-RateLimit-Requests-Expire`` (epoch ms).
        # Если есть стандартный ``Retry-After`` — уважаем его в первую очередь.
        header = response.headers.get("Retry-After")
        if header is not None:
            try:
                return max(float(header), 0.0)
            except ValueError:
                return None
        expire = response.headers.get("X-RateLimit-Requests-Expire")
        if expire is None:
            return None
        try:
            expire_ms = float(expire)
        except ValueError:
            return None
        wait_s = expire_ms / 1000 - time.time()
        return max(wait_s, 0.0)

    @staticmethod
    def _unwrap_payload(response: httpx.Response, path: str) -> Any:
        """Распаковать стандартный конверт BingX ``{code, msg, data}``.

        Бизнес-ошибки (``code != 0``) поднимают APIError несмотря на HTTP 200.
        """
        try:
            payload = response.json()
        except ValueError as e:
            raise InvalidResponseError(f"non-JSON response from {path}: {e}") from e
        if not isinstance(payload, dict):
            raise InvalidResponseError(
                f"BingX envelope must be object, got {type(payload).__name__} at {path}"
            )
        code = payload.get("code")
        if code is None:
            raise InvalidResponseError(f"BingX envelope missing 'code' at {path}: {payload!r}")
        if code != 0:
            raise APIError(int(code), str(payload.get("msg", "")), endpoint=path)
        if "data" not in payload:
            raise InvalidResponseError(f"BingX envelope missing 'data' at {path}: {payload!r}")
        return payload["data"]
