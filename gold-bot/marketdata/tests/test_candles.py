"""Тесты data layer: пагинация, дедуп, parquet round-trip."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from exchanges.models import OHLCV
from marketdata.candles import (
    candles_path,
    download_ohlcv,
    load_parquet,
    save_parquet,
    timeframe_to_ms,
)


def _c(ts: int, close: str = "1") -> OHLCV:
    return OHLCV(
        timestamp=ts,
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal(close),
        volume=Decimal("100"),
    )


class _FakeAdapter:
    """Отдаёт заранее заданные страницы в зависимости от номера вызова."""

    def __init__(self, pages: list[list[OHLCV]]) -> None:
        self._pages = pages
        self.calls: list[int | None] = []

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int | None = None
    ) -> list[OHLCV]:
        self.calls.append(since)
        idx = len(self.calls) - 1
        return self._pages[idx] if idx < len(self._pages) else []


@pytest.mark.parametrize(
    ("tf", "ms"),
    [("1m", 60_000), ("15m", 900_000), ("1h", 3_600_000), ("4h", 14_400_000), ("1d", 86_400_000)],
)
def test_timeframe_to_ms(tf: str, ms: int) -> None:
    assert timeframe_to_ms(tf) == ms


def test_timeframe_to_ms_invalid() -> None:
    with pytest.raises(ValueError):
        timeframe_to_ms("abc")


def test_timeframe_to_ms_zero() -> None:
    with pytest.raises(ValueError):
        timeframe_to_ms("0m")


@pytest.mark.asyncio
async def test_download_paginates_until_empty() -> None:
    adapter = _FakeAdapter(
        [
            [_c(1000), _c(2000)],
            [_c(3000), _c(4000)],
            [],
        ]
    )
    candles = await download_ohlcv(adapter, "BTC-USDT", "1m", start_ms=1000)
    assert [c.timestamp for c in candles] == [1000, 2000, 3000, 4000]
    # курсор продвигается за последний timestamp каждой страницы: 2000→2001, 4000→4001
    assert adapter.calls == [1000, 2001, 4001]


@pytest.mark.asyncio
async def test_download_dedups_overlapping_pages() -> None:
    adapter = _FakeAdapter(
        [
            [_c(1000), _c(2000)],
            [_c(2000, close="9"), _c(3000)],  # 2000 повторяется — дедуп, первая версия
            [],
        ]
    )
    candles = await download_ohlcv(adapter, "BTC-USDT", "1m", start_ms=1000)
    assert [c.timestamp for c in candles] == [1000, 2000, 3000]
    assert candles[1].close == Decimal("1")  # сохранена первая версия 2000


@pytest.mark.asyncio
async def test_download_stops_at_end_ms() -> None:
    adapter = _FakeAdapter([[_c(1000), _c(2000), _c(3000)]])
    candles = await download_ohlcv(adapter, "BTC-USDT", "1m", start_ms=1000, end_ms=2000)
    assert [c.timestamp for c in candles] == [1000, 2000]


@pytest.mark.asyncio
async def test_download_no_progress_breaks() -> None:
    # страница всегда одна и та же — продвижения нет, не должно зациклиться
    adapter = _FakeAdapter([[_c(500)], [_c(500)]])
    candles = await download_ohlcv(adapter, "BTC-USDT", "1m", start_ms=1000)
    assert [c.timestamp for c in candles] == [500]


def test_parquet_round_trip_preserves_decimal(tmp_path: Path) -> None:
    candles = [
        _c(1000, close="100.123456789"),
        _c(2000, close="0.000000001"),
    ]
    path = tmp_path / "btc.parquet"
    save_parquet(candles, path)
    loaded = load_parquet(path)
    assert [c.timestamp for c in loaded] == [1000, 2000]
    assert loaded[0].close == Decimal("100.123456789")
    assert loaded[1].close == Decimal("0.000000001")


def test_candles_path_normalizes_symbol() -> None:
    p = candles_path("/data", "bybit", "BTC-USDT", "15m")
    assert p == Path("/data/candles/bybit/BTC_USDT_USDT/15m.parquet")
