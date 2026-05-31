"""Тесты BybitClient: envelope-парсинг, retry, signing-headers, AuthError."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from adapters.bybit.client import BybitClient
from adapters.bybit.exceptions import APIError, AuthError, RateLimited
from adapters.bybit.settings import BybitSettings


def _ok_envelope(result: dict[str, Any] | list[Any] | None = None) -> dict[str, Any]:
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": result if result is not None else {},
        "retExtInfo": {},
        "time": 1700000000000,
    }


def _err_envelope(code: int, msg: str) -> dict[str, Any]:
    return {
        "retCode": code,
        "retMsg": msg,
        "result": {},
        "retExtInfo": {},
        "time": 1700000000000,
    }


_TESTNET_URL = "https://api-testnet.bybit.com"


@pytest.mark.asyncio
async def test_public_get_parses_envelope() -> None:
    """public_get возвращает result (без retCode/retMsg)."""
    settings = BybitSettings(_env_file=None, env="testnet")
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.get("/v5/market/tickers").mock(
            return_value=httpx.Response(200, json=_ok_envelope({"list": [{"symbol": "BTCUSDT"}]}))
        )
        async with BybitClient(settings=settings) as c:
            data = await c.public_get("/v5/market/tickers", params={"category": "linear"})
    assert data == {"list": [{"symbol": "BTCUSDT"}]}


@pytest.mark.asyncio
async def test_api_error_raised_on_nonzero_retcode() -> None:
    """retCode != 0 → APIError(code, msg)."""
    settings = BybitSettings(_env_file=None, env="testnet")
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.get("/v5/market/tickers").mock(
            return_value=httpx.Response(200, json=_err_envelope(110001, "bad symbol"))
        )
        async with BybitClient(settings=settings) as c:
            with pytest.raises(APIError) as exc_info:
                await c.public_get("/v5/market/tickers", params={"category": "linear"})
    assert exc_info.value.code == 110001
    assert "bad symbol" in exc_info.value.message


@pytest.mark.asyncio
async def test_auth_error_on_invalid_key_codes() -> None:
    """retCode 10003/10004 → AuthError (не APIError)."""
    settings = BybitSettings(
        _env_file=None,
        env="testnet",
        testnet_api_key="k",
        testnet_api_secret="s",
    )
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.get("/v5/account/wallet-balance").mock(
            return_value=httpx.Response(200, json=_err_envelope(10003, "invalid key"))
        )
        async with BybitClient(settings=settings) as c:
            with pytest.raises(AuthError):
                await c.signed_get("/v5/account/wallet-balance", params={})


@pytest.mark.asyncio
async def test_signed_get_sets_required_headers() -> None:
    """Signed-вызов проставляет 4 заголовка X-BAPI-*."""
    settings = BybitSettings(
        _env_file=None,
        env="testnet",
        testnet_api_key="abc",
        testnet_api_secret="secret",
    )
    captured: dict[str, str] = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.headers))
        return httpx.Response(200, json=_ok_envelope({}))

    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.get("/v5/account/wallet-balance").mock(side_effect=capture)
        async with BybitClient(settings=settings) as c:
            await c.signed_get("/v5/account/wallet-balance", params={"accountType": "UNIFIED"})
    assert captured.get("x-bapi-api-key") == "abc"
    assert "x-bapi-sign" in captured
    assert len(captured["x-bapi-sign"]) == 64  # hex sha256
    assert captured.get("x-bapi-timestamp") is not None
    assert captured.get("x-bapi-recv-window") == "5000"


@pytest.mark.asyncio
async def test_signed_without_keys_raises_auth_error() -> None:
    """Сигнальный запрос без ключей → AuthError, в сеть не идём."""
    settings = BybitSettings(_env_file=None, env="testnet")
    async with BybitClient(settings=settings) as c:
        with pytest.raises(AuthError, match="requires keys"):
            await c.signed_get("/v5/account/wallet-balance", params={})


@pytest.mark.asyncio
async def test_retry_on_5xx_then_success() -> None:
    """GET ретраит 500 → следующая попытка 200, итог — успех."""
    settings = BybitSettings(_env_file=None, env="testnet")
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        route = mock.get("/v5/market/time")
        route.side_effect = [
            httpx.Response(500, text="oops"),
            httpx.Response(200, json=_ok_envelope({"timeSecond": "1700000000"})),
        ]
        async with BybitClient(settings=settings, retries=2, timeout_s=2.0) as c:
            data = await c.public_get("/v5/market/time", params={})
    assert data["timeSecond"] == "1700000000"


@pytest.mark.asyncio
async def test_sync_time_sets_offset() -> None:
    """sync_time опрашивает /v5/market/time и фиксирует offset."""
    settings = BybitSettings(_env_file=None, env="testnet")
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        # Сервер «впереди» на 60 сек.
        mock.get("/v5/market/time").mock(
            return_value=httpx.Response(200, json=_ok_envelope({"timeSecond": str(2_000_000_060)}))
        )
        async with BybitClient(settings=settings) as c:
            offset = await c.sync_time()
    # Точную дельту не предсказать (зависит от now()), но offset должен
    # быть в районе (server - local).
    assert offset > 0


@pytest.mark.asyncio
async def test_rate_limit_envelope_retries_then_succeeds() -> None:
    """retCode 10006 «Too many visits» → retry → следующий ответ ok."""
    settings = BybitSettings(_env_file=None, env="testnet")
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        route = mock.get("/v5/market/time")
        route.side_effect = [
            httpx.Response(200, json=_err_envelope(10006, "Too many visits!")),
            httpx.Response(200, json=_ok_envelope({"timeSecond": "1700000000"})),
        ]
        async with BybitClient(settings=settings, retries=2, timeout_s=2.0) as c:
            data = await c.public_get("/v5/market/time", params={})
    assert data["timeSecond"] == "1700000000"
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_rate_limit_envelope_exhausted_raises() -> None:
    """Если ретраи исчерпаны и rate-limit держится — RateLimited (subclass APIError)."""
    settings = BybitSettings(_env_file=None, env="testnet")
    async with respx.mock(base_url=_TESTNET_URL) as mock:
        mock.get("/v5/market/time").mock(
            return_value=httpx.Response(200, json=_err_envelope(10006, "Too many visits!"))
        )
        async with BybitClient(settings=settings, retries=2, timeout_s=2.0) as c:
            with pytest.raises(RateLimited) as exc_info:
                await c.public_get("/v5/market/time", params={})
    assert exc_info.value.code == 10006
    # RateLimited — подкласс APIError, ловится и тем и тем.
    assert isinstance(exc_info.value, APIError)


@pytest.mark.asyncio
async def test_rate_limit_envelope_codes_10018_10429() -> None:
    """10018 (IP rate limit) и 10429 (request rate limit) тоже RateLimited."""
    settings = BybitSettings(_env_file=None, env="testnet")
    for code in (10018, 10429):
        async with respx.mock(base_url=_TESTNET_URL) as mock:
            mock.get("/v5/market/time").mock(
                return_value=httpx.Response(200, json=_err_envelope(code, "rate limited"))
            )
            async with BybitClient(settings=settings, retries=1, timeout_s=2.0) as c:
                with pytest.raises(RateLimited) as exc_info:
                    await c.public_get("/v5/market/time", params={})
        assert exc_info.value.code == code
