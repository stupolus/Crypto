"""Тесты live OI-провайдера (план 21 фаза 21.3)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from core.signals import (
    OpenInterestProvider,
    RollingOpenInterestProvider,
    poll_open_interest,
)


def test_protocol_compliance() -> None:
    assert isinstance(RollingOpenInterestProvider(), OpenInterestProvider)


def test_record_and_get_series() -> None:
    p = RollingOpenInterestProvider()
    p.record("BTC-USDT", 100, Decimal("1000"))
    p.record("BTC-USDT", 200, Decimal("1100"))
    p.record("BTC-USDT", 300, Decimal("1200"))
    assert p.get_series("BTC-USDT", 250, n=5) == [Decimal("1000"), Decimal("1100")]
    assert p.get_series("BTC-USDT", 300, n=2) == [Decimal("1100"), Decimal("1200")]
    assert p.get_series("ETH-USDT", 300, n=5) == []


def test_duplicate_ts_ignored() -> None:
    p = RollingOpenInterestProvider()
    p.record("X", 100, Decimal("1"))
    p.record("X", 100, Decimal("999"))  # тот же ts → игнор
    assert p.get_series("X", 100, n=5) == [Decimal("1")]


def test_maxlen_bounds_memory() -> None:
    p = RollingOpenInterestProvider(maxlen=3)
    for i in range(10):
        p.record("X", i, Decimal(str(i)))
    s = p.get_series("X", 99, n=10)
    assert s == [Decimal("7"), Decimal("8"), Decimal("9")]  # только последние 3


@pytest.mark.asyncio
async def test_poll_open_interest_records() -> None:
    p = RollingOpenInterestProvider()
    api = AsyncMock()
    api.get_open_interest.return_value = type(
        "OI", (), {"time_ms": 1234, "open_interest": Decimal("555.5")}
    )()
    ok = await poll_open_interest(api, "BTC-USDT", p)
    assert ok is True
    assert p.get_series("BTC-USDT", 9999, n=1) == [Decimal("555.5")]


@pytest.mark.asyncio
async def test_poll_open_interest_swallows_errors() -> None:
    p = RollingOpenInterestProvider()
    api = AsyncMock()
    api.get_open_interest.side_effect = RuntimeError("network")
    ok = await poll_open_interest(api, "BTC-USDT", p)
    assert ok is False
    assert p.get_series("BTC-USDT", 9999, n=1) == []
