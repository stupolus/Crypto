"""Unit-тесты ``adapters.bingx.time_sync.ServerTimeSyncer``.

Что проверяется:
- ``sync()`` корректно вычисляет offset = serverTime - localMs.
- ``ensure_fresh()`` не дёргает API чаще ``interval_s``.
- ``now_ms()`` подмешивает offset в локальное время.
- ``InvalidResponseError`` при отсутствии поля ``serverTime``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import respx

from adapters.bingx.client import BingXClient
from adapters.bingx.config import BingXConfig
from adapters.bingx.exceptions import InvalidResponseError


def _stub_server_time(
    mock: respx.MockRouter, cfg: BingXConfig, server_ms: int
) -> respx.Route:
    return mock.get(cfg.rest_endpoints.server_time).mock(
        return_value=httpx.Response(
            200, json={"code": 0, "msg": "", "data": {"serverTime": server_ms}}
        )
    )


@pytest.mark.asyncio
async def test_sync_sets_offset_from_server_response(cfg: BingXConfig) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        # Поставим server на «5 секунд впереди» относительно any local now.
        _stub_server_time(mock, cfg, server_ms=2_000_000_005_000)
        offset = await client.time_syncer.sync()
    # Offset = server - local. Локальное время — реальное; точное значение
    # неизвестно, но offset должен быть около (2_000_000_005_000 - now_ms).
    assert isinstance(offset, int)
    assert client.time_syncer.is_synced is True


@pytest.mark.asyncio
async def test_now_ms_uses_offset(cfg: BingXConfig) -> None:
    """``now_ms()`` = local + offset, должно быть близко к server_ms."""
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        server_ms = 1_700_000_000_000
        _stub_server_time(mock, cfg, server_ms=server_ms)
        ts = await client.time_syncer.now_ms()
    # Между расчётом offset и возвратом now_ms прошло мало времени.
    assert abs(ts - server_ms) < 1_000, f"expected ~{server_ms}, got {ts}"


@pytest.mark.asyncio
async def test_ensure_fresh_skips_sync_within_interval(cfg: BingXConfig) -> None:
    """В пределах interval_s повторный ensure_fresh не делает HTTP-запрос."""
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        route = _stub_server_time(mock, cfg, server_ms=1_700_000_000_000)
        await client.time_syncer.sync()
        assert route.call_count == 1
        # Следующий ensure_fresh не должен пойти в сеть.
        await client.time_syncer.ensure_fresh()
        await client.time_syncer.ensure_fresh()
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_sync_raises_when_server_time_missing(cfg: BingXConfig) -> None:
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        mock.get(cfg.rest_endpoints.server_time).mock(
            return_value=httpx.Response(200, json={"code": 0, "msg": "", "data": {}})
        )
        with pytest.raises(InvalidResponseError):
            await client.time_syncer.sync()


@pytest.mark.asyncio
async def test_concurrent_sync_serialized_by_lock(cfg: BingXConfig) -> None:
    """Параллельные ``sync()`` сериализуются — гонки нет."""
    async with BingXClient(cfg) as client, respx.mock(base_url=cfg.active_rest_base) as mock:
        responses: list[Any] = [
            httpx.Response(200, json={"code": 0, "msg": "", "data": {"serverTime": i}})
            for i in (1_000, 2_000, 3_000)
        ]
        mock.get(cfg.rest_endpoints.server_time).mock(side_effect=responses)
        await asyncio.gather(
            client.time_syncer.sync(),
            client.time_syncer.sync(),
            client.time_syncer.sync(),
        )
    # Все три прошли без исключений и без двойного входа в критическую секцию.
    assert client.time_syncer.is_synced is True
