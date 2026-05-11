"""Async HTTP-клиент BingX.

Слой ниже ``public.py`` / ``private.py``: знает про подпись, rate limit,
retry, разбор бизнес-ошибок ``code != 0``. Сами эндпоинты и
pydantic-парсинг — на уровне выше.

Дизайн-решения:
- ``httpx.AsyncClient`` (поддержка HTTP/1.1, async, моки через respx).
- Token bucket для глобального market data лимита (350/10s по конфигу,
  что 70% от официальных 500/10s — буфер на всплески, см. plans/01 §10 п.5).
- Retry-policy: только идемпотентные методы (GET/PUT/DELETE) + ретраимые
  HTTP-статусы из конфига (429, 5xx). POST не ретраим автоматически —
  идемпотентность управляется через ``client_order_id`` в фазе 0.D.
- HMAC-подпись: алгоритм в ``sign_query`` (ASCII-сортировка, без URL-encoding
  в подписной строке). Источник: docs-v3 → Quick Start → Signature.
- Timestamp в подписи берётся из ``ServerTimeSyncer`` (см. ``time_sync.py``),
  не из локального ``time.time()`` — иначе расхождение часов > recvWindow
  ловит ``code=109400``.
- Если signed-запрос упал на ``timestamp out of recvWindow`` — однократно
  принудительно ресинкаем время и повторяем. Это митигация причины №3
  из plans/04 §8 (плывущие часы VPS / suspend/resume).

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
from adapters.bingx.settings import BingXSettings
from adapters.bingx.time_sync import ServerTimeSyncer

# Бизнес-коды BingX, означающие «локальный timestamp не попадает в recvWindow
# серверного времени». 100400 — generic «parameter error» из которого BingX
# часто возвращает timestamp-проблемы; 109400 — задокументировано как
# конкретно timestamp. Дополнительная страховка — substring в message.
_TIMESTAMP_ERROR_CODES = frozenset({100400, 109400})
_TIMESTAMP_ERROR_HINTS = ("timestamp", "recvwindow", "recv_window")


def _is_timestamp_error(err: APIError) -> bool:
    if err.code in _TIMESTAMP_ERROR_CODES:
        return True
    msg = err.message.lower()
    return any(hint in msg for hint in _TIMESTAMP_ERROR_HINTS)


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

        async with BingXClient(settings=load_settings()) as client:
            balance = await client.request_signed(
                "GET", "/openApi/swap/v3/user/balance"
            )

    Ключи: приоритет explicit ``api_key``/``api_secret`` >
    ``settings.active_key``/``settings.active_secret`` > ``None``. Без ключей
    publicAPI работает, ``request_signed`` бросает ``AuthError``.
    """

    def __init__(
        self,
        config: BingXConfig | None = None,
        *,
        settings: BingXSettings | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config or get_default_config()
        # Settings.env (.env / переменные окружения) имеет приоритет над YAML —
        # это даёт безопасный путь «положил BINGX_ENV=vst → пошёл на VST», без
        # необходимости редактировать config.yaml. Без settings — берём YAML.
        if settings is not None and settings.env != self._config.env:
            self._config = self._config.model_copy(update={"env": settings.env})
        # explicit > settings > None
        self._api_key = api_key if api_key is not None else (
            settings.active_key if settings is not None else None
        )
        self._api_secret = api_secret if api_secret is not None else (
            settings.active_secret if settings is not None else None
        )
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
        self._time_syncer = ServerTimeSyncer(
            client=self,
            server_time_path=self._config.rest_endpoints.server_time,
            interval_s=self._config.signing.server_time_resync_interval_s,
        )

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

    # ── Свойства для PrivateAPI/тестов ─────────────────────────────────────
    @property
    def config(self) -> BingXConfig:
        return self._config

    @property
    def time_syncer(self) -> ServerTimeSyncer:
        return self._time_syncer

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key) and bool(self._api_secret)

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
        raw_response: bool = False,
    ) -> Any:
        """Приватный (подписанный) запрос.

        Алгоритм:
        1. timestamp = ``time_syncer.now_ms()`` (с lazy-sync при необходимости).
        2. recvWindow из конфига.
        3. ASCII-sort + canonical string + HMAC-SHA256(secret).
        4. Header ``X-BX-APIKEY``.
        5. Если BingX вернул timestamp-ошибку — форсим resync и повторяем
           один раз. Дальше — поднимаем APIError.

        ``raw_response=True`` отключает разворачивание envelope
        ``{code, msg, data}``: возвращает сырой JSON-объект.
        Нужен для эндпоинтов, не следующих стандартному формату
        (квирк §7 п.34: ``/openApi/user/auth/userDataStream``).
        """
        if not self._api_key or not self._api_secret:
            raise AuthError(
                "request_signed requires api_key/api_secret; "
                "set BINGX_VST_API_KEY/BINGX_VST_API_SECRET in .env"
            )
        try:
            return await self._do_signed(
                method, path, params=params, raw_response=raw_response
            )
        except APIError as err:
            if not _is_timestamp_error(err):
                raise
            # Часы поплыли — форсим resync и повторяем ровно один раз.
            await self._time_syncer.sync()
            return await self._do_signed(
                method, path, params=params, raw_response=raw_response
            )

    async def _do_signed(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None,
        raw_response: bool = False,
    ) -> Any:
        # Два подтверждённых квирка live BingX VST (2026-05-11, см. plans/01 §7):
        # 1. Передача `recvWindow` в params/подписи приводит к
        #    `code=100001 "Signature verification failed"`, даже когда
        #    значение совпадает с дефолтом docs (5000ms). Не отправляем
        #    recvWindow вовсе — BingX применит server-side default.
        # 2. BingX подписывает query string РОВНО в том порядке, в котором
        #    она пришла в URL — не пересортирует. Поэтому params должны
        #    уйти в httpx в alpha-sorted порядке (Python dict сохраняет
        #    insertion order; httpx сохраняет порядок dict при сборке URL).
        #    Иначе canonical и URL-query разойдутся → reject.
        assert self._api_secret is not None  # checked by caller
        assert self._api_key is not None
        ts_ms = await self._time_syncer.now_ms()
        biz: dict[str, Any] = dict(params or {})
        biz["timestamp"] = ts_ms
        # Sorted dict: сортируем по ключу, сохраняем порядок для httpx.
        sorted_biz: dict[str, Any] = dict(sorted(biz.items()))
        signature = sign_query(sorted_biz, self._api_secret)
        sorted_biz["signature"] = signature
        await self._market_bucket.acquire()
        headers = {self._config.signing.api_key_header: self._api_key}
        return await self._send_with_retry(
            method, path, params=sorted_biz, headers=headers, raw_response=raw_response
        )

    # ── Внутренности ───────────────────────────────────────────────────────
    async def _send_with_retry(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        raw_response: bool = False,
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
            if raw_response:
                return self._parse_raw_json(response, path)
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
    def _parse_raw_json(response: httpx.Response, path: str) -> Any:
        """Распарсить JSON без проверки envelope. Для эндпоинтов вне
        стандартного формата (квирк §7 п.34: userDataStream).

        Квирк §7 п.35: PUT/DELETE userDataStream возвращают **пустой body**
        (не JSON). Возвращаем `{}` чтобы PrivateAPI не падал.
        """
        text = response.text
        if not text or not text.strip():
            return {}
        try:
            return response.json()
        except ValueError as e:
            raise InvalidResponseError(f"non-JSON response from {path}: {e}") from e

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
