"""Async HTTP-клиент Bybit V5.

Слой ниже ``public.py``/``private.py``: знает подпись, ретраи, разбор
бизнес-ошибок (``retCode != 0``). Эндпоинты и pydantic-парсинг —
уровнем выше.

Дизайн:
- ``httpx.AsyncClient`` (моки через respx).
- Retry на 429/5xx с экспоненциальным бэкоффом (только GET/DELETE,
  POST не ретраим — идемпотентность через ``orderLinkId``).
- HMAC-подпись по формуле `timestamp+apiKey+recvWindow+payload` (см. signing.py).
- Time-sync: однократно при подключении (`/v5/market/time`).
- При AuthError → не ретраим (плохой ключ — фейлим быстро).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlencode

import httpx

from adapters.bybit.exceptions import APIError, AuthError, NetworkError
from adapters.bybit.settings import BybitSettings
from adapters.bybit.signing import sign_query

logger = logging.getLogger(__name__)

# Маскирование секретов в логах.
_SENSITIVE_HEADERS_CI = ("x-bapi-api-key", "x-bapi-sign")
_MASK = "***"


def mask_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Заменить значения чувствительных заголовков на ``***``."""
    out: dict[str, str] = {}
    for k, v in headers.items():
        out[k] = _MASK if k.lower() in _SENSITIVE_HEADERS_CI else v
    return out


class BybitClient:
    """Async HTTP-клиент Bybit V5.

    Использование:
        async with BybitClient(settings=BybitSettings()) as c:
            res = await c.public_get("/v5/market/tickers", params={"category": "linear"})
    """

    DEFAULT_TIMEOUT_S = 10.0
    DEFAULT_RETRIES = 3
    RETRY_STATUSES = (429, 500, 502, 503, 504)

    def __init__(
        self,
        *,
        settings: BybitSettings,
        timeout_s: float | None = None,
        retries: int | None = None,
        base_url: str | None = None,
    ) -> None:
        self._settings = settings
        self._timeout_s = timeout_s if timeout_s is not None else self.DEFAULT_TIMEOUT_S
        self._retries = retries if retries is not None else self.DEFAULT_RETRIES
        self._base_url = base_url or settings.rest_base_url
        self._client: httpx.AsyncClient | None = None
        # Server time offset (server_ms - local_ms). Заполняется при первом
        # signed-вызове или ``sync_time()``. Без него используем локальное время.
        self._time_offset_ms: int = 0

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout_s,
            headers={"User-Agent": "crypto-bot/bybit"},
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Time sync ────────────────────────────────────────────────────────────

    async def sync_time(self) -> int:
        """Опросить ``/v5/market/time`` и зафиксировать offset (ms).

        Возвращает offset = server_ms - local_ms.
        """
        data = await self.public_get("/v5/market/time", params={})
        # Bybit V5: result.timeSecond, result.timeNano
        ts_str = data.get("timeSecond")
        if ts_str is None:
            raise APIError(0, "time endpoint missing timeSecond", "/v5/market/time")
        server_ms = int(ts_str) * 1000
        local_ms = int(time.time() * 1000)
        self._time_offset_ms = server_ms - local_ms
        return self._time_offset_ms

    def _now_ms(self) -> int:
        """Текущее ms по серверу (локальное + offset)."""
        return int(time.time() * 1000) + self._time_offset_ms

    # ── Public ───────────────────────────────────────────────────────────────

    async def public_get(
        self, path: str, *, params: Mapping[str, str | int | float]
    ) -> dict[str, Any]:
        """GET без подписи. Парсит V5-envelope, raise APIError если retCode != 0."""
        return await self._request("GET", path, params=params, signed=False)

    # ── Signed ───────────────────────────────────────────────────────────────

    async def signed_get(
        self, path: str, *, params: Mapping[str, str | int | float]
    ) -> dict[str, Any]:
        """GET с подписью."""
        return await self._request("GET", path, params=params, signed=True)

    async def signed_post(self, path: str, *, body: Mapping[str, Any]) -> dict[str, Any]:
        """POST с подписью (JSON-body)."""
        return await self._request("POST", path, body=body, signed=True)

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int | float] | None = None,
        body: Mapping[str, Any] | None = None,
        signed: bool = False,
    ) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("BybitClient used outside `async with`")
        if signed and not self._settings.has_credentials():
            raise AuthError(f"Bybit signed request requires keys (env={self._settings.env})")

        headers: dict[str, str] = {}
        if signed:
            assert self._settings.active_key is not None
            assert self._settings.active_secret is not None
            timestamp_ms = self._now_ms()
            recv_window = self._settings.recv_window_ms

            if method == "GET":
                payload = urlencode(sorted((params or {}).items())) if params else ""
            else:
                # POST: payload = raw JSON body как строка. Используем httpx
                # сериализацию ниже, здесь воспроизводим тот же текст.
                import json

                payload = json.dumps(body or {}, separators=(",", ":"), sort_keys=True)
            signature = sign_query(
                api_secret=self._settings.active_secret,
                timestamp_ms=timestamp_ms,
                api_key=self._settings.active_key,
                recv_window_ms=recv_window,
                payload=payload,
            )
            headers.update(
                {
                    "X-BAPI-API-KEY": self._settings.active_key,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-TIMESTAMP": str(timestamp_ms),
                    "X-BAPI-RECV-WINDOW": str(recv_window),
                }
            )
            if method == "POST":
                headers["Content-Type"] = "application/json"

        # Retries (только GET/DELETE).
        is_idempotent = method in ("GET", "DELETE")
        retries = self._retries if is_idempotent else 1

        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                if method == "GET":
                    resp = await self._client.get(path, params=params, headers=headers)
                elif method == "POST":
                    # Сериализуем тем же способом, что подписали.
                    import json

                    text = json.dumps(body or {}, separators=(",", ":"), sort_keys=True)
                    resp = await self._client.post(path, content=text, headers=headers)
                else:
                    raise ValueError(f"Unsupported method: {method}")
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as e:
                last_exc = NetworkError(f"{method} {path}: {type(e).__name__}: {e}")
                if attempt + 1 < retries:
                    await asyncio.sleep(2 ** (attempt + 1))
                    continue
                raise last_exc from e

            if resp.status_code in self.RETRY_STATUSES and attempt + 1 < retries:
                await asyncio.sleep(2 ** (attempt + 1))
                continue
            break

        return self._parse_envelope(resp, path)

    def _parse_envelope(self, resp: httpx.Response, path: str) -> dict[str, Any]:
        """V5-envelope: ``{retCode, retMsg, result, retExtInfo, time}``.

        Поднимает ``APIError`` если ``retCode != 0``. Возвращает
        содержимое ``result`` как dict (для public).
        """
        if resp.status_code != 200:
            raise NetworkError(f"{path}: HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            data = resp.json()
        except ValueError as e:
            raise NetworkError(f"{path}: non-JSON response: {resp.text[:200]}") from e

        if not isinstance(data, dict):
            raise NetworkError(f"{path}: envelope is not dict: {data}")
        ret_code = data.get("retCode")
        if ret_code != 0:
            ret_msg = str(data.get("retMsg", ""))
            # Auth-классные коды Bybit: 10003 (invalid api key), 10004 (sign),
            # 10005 (permissions), 10006 (rate limit ip), 10007 (recv window).
            if ret_code in (10003, 10004):
                raise AuthError(f"{path}: code={ret_code} msg={ret_msg}")
            raise APIError(int(ret_code or 0), ret_msg, path)
        result = data.get("result")
        if result is None:
            return {}
        if not isinstance(result, dict):
            return {"_value": result}
        return result
