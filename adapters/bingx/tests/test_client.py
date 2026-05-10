"""Unit-тесты HTTP-клиента BingX.

Цель: покрыть критичные пути транспорта в изоляции от живого API.

Что проверяется:
- HMAC-подпись по тест-векторам сортировки и алгоритма (docs-v3 Query
  String Example).
- Распаковка envelope ``{code, msg, data}``: успех / бизнес-ошибка / битый
  envelope.
- Маппинг HTTP-статусов на иерархию исключений (401 → AuthError, 429 →
  RateLimited, 5xx → ServerError, прочие 4xx → APIError).
- Retry-policy: на 5xx делает повтор, на 4xx не делает.
- Token bucket rate limit действительно блокирует при переполнении.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from typing import Any

import httpx
import pytest
import respx

from adapters.bingx.client import BingXClient, _TokenBucket, sign_query
from adapters.bingx.config import BingXConfig
from adapters.bingx.exceptions import (
    APIError,
    AuthError,
    InvalidResponseError,
    RateLimited,
    ServerError,
)

# ── sign_query ──────────────────────────────────────────────────────────────


def test_sign_query_sorts_keys_alphabetically_and_uses_hmac_sha256() -> None:
    """Подпись = HMAC-SHA256 над сортированной по ASCII канонической строкой."""
    params = {"timestamp": 1700000000000, "symbol": "BTC-USDT", "side": "BUY"}
    secret = "supersecret"

    actual = sign_query(params, secret)

    canonical = "side=BUY&symbol=BTC-USDT&timestamp=1700000000000"
    expected = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    assert actual == expected
    assert len(actual) == 64
    assert actual == actual.lower()


def test_sign_query_no_url_encoding_in_signed_string() -> None:
    """Подпись считается БЕЗ URL-encoding (квирк §7 п.18 plans/01)."""
    params = {"a": "x y", "b": "1=2"}
    actual = sign_query(params, "k")
    expected = hmac.new(b"k", b"a=x y&b=1=2", hashlib.sha256).hexdigest()
    assert actual == expected


# ── envelope ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_public_returns_data_on_success(
    cfg: BingXConfig, server_time_payload: dict[str, Any]
) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.server_time).mock(
            return_value=httpx.Response(200, json=server_time_payload)
        )
        data = await client.request_public("GET", cfg.rest_endpoints.server_time)
    assert data == {"serverTime": 1758297600123}


@pytest.mark.asyncio
async def test_request_public_raises_api_error_when_code_non_zero(cfg: BingXConfig) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.contracts).mock(
            return_value=httpx.Response(
                200, json={"code": 100400, "msg": "bad symbol", "data": None}
            )
        )
        with pytest.raises(APIError) as excinfo:
            await client.request_public("GET", cfg.rest_endpoints.contracts)
    assert excinfo.value.code == 100400
    assert "bad symbol" in str(excinfo.value)


@pytest.mark.asyncio
async def test_request_public_raises_invalid_response_on_non_json(cfg: BingXConfig) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.contracts).mock(
            return_value=httpx.Response(200, content=b"<html>oops</html>")
        )
        with pytest.raises(InvalidResponseError):
            await client.request_public("GET", cfg.rest_endpoints.contracts)


@pytest.mark.asyncio
async def test_request_public_raises_invalid_response_on_missing_envelope_fields(
    cfg: BingXConfig,
) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.contracts).mock(
            return_value=httpx.Response(200, json={"data": [], "msg": "ok"})  # no code
        )
        with pytest.raises(InvalidResponseError):
            await client.request_public("GET", cfg.rest_endpoints.contracts)


# ── HTTP-статусы → иерархия исключений ──────────────────────────────────────


@pytest.mark.asyncio
async def test_request_public_raises_auth_error_on_401(cfg: BingXConfig) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.contracts).mock(
            return_value=httpx.Response(401, json={"code": 100401, "msg": "unauthorized"})
        )
        with pytest.raises(AuthError):
            await client.request_public("GET", cfg.rest_endpoints.contracts)


@pytest.mark.asyncio
async def test_request_public_retries_on_5xx_then_succeeds(
    cfg: BingXConfig, server_time_payload: dict[str, Any]
) -> None:
    """5xx ретраится; на втором ответе — успех."""
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = mock.get(cfg.rest_endpoints.server_time).mock(
            side_effect=[
                httpx.Response(503, text="upstream busy"),
                httpx.Response(200, json=server_time_payload),
            ]
        )
        data = await client.request_public("GET", cfg.rest_endpoints.server_time)
    assert route.call_count == 2
    assert data == {"serverTime": 1758297600123}


@pytest.mark.asyncio
async def test_request_public_raises_server_error_after_max_attempts(cfg: BingXConfig) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = mock.get(cfg.rest_endpoints.server_time).mock(
            return_value=httpx.Response(500, text="boom")
        )
        with pytest.raises(ServerError):
            await client.request_public("GET", cfg.rest_endpoints.server_time)
    assert route.call_count == cfg.http.retry.max_attempts


@pytest.mark.asyncio
async def test_request_public_raises_rate_limited_on_429(cfg: BingXConfig) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.server_time).mock(
            return_value=httpx.Response(429, headers={"Retry-After": "0"}, text="rate limited")
        )
        with pytest.raises(RateLimited):
            await client.request_public("GET", cfg.rest_endpoints.server_time)


@pytest.mark.asyncio
async def test_request_public_does_not_retry_on_400(cfg: BingXConfig) -> None:
    """4xx (кроме 429/401) — наша ошибка, не повторяем."""
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = mock.get(cfg.rest_endpoints.server_time).mock(
            return_value=httpx.Response(400, text="bad request")
        )
        with pytest.raises(APIError) as excinfo:
            await client.request_public("GET", cfg.rest_endpoints.server_time)
    assert route.call_count == 1
    assert excinfo.value.code == 400


# ── приватный запрос требует ключей ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_signed_without_keys_raises_auth_error(cfg: BingXConfig) -> None:
    async with BingXClient(cfg) as client:
        with pytest.raises(AuthError):
            await client.request_signed("GET", "/openApi/swap/v2/user/balance")


# ── Token bucket ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_bucket_blocks_when_over_capacity() -> None:
    """Третий вызов должен ждать освобождения слота примерно ``window_s``."""
    bucket = _TokenBucket(capacity=2, window_s=0.2)
    await bucket.acquire()
    await bucket.acquire()
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    # Допускаем небольшой джиттер планировщика.
    assert 0.15 <= elapsed <= 0.5, f"expected ~0.2s wait, got {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_token_bucket_concurrent_acquire_does_not_exceed_capacity() -> None:
    bucket = _TokenBucket(capacity=3, window_s=0.1)
    start = time.monotonic()
    await asyncio.gather(*[bucket.acquire() for _ in range(6)])
    elapsed = time.monotonic() - start
    # 6 запросов / 3 на окно → должно занять минимум одно окно.
    assert elapsed >= 0.09, f"expected >= ~0.1s, got {elapsed:.3f}s"
