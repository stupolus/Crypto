"""Тесты PaperFeed: только закрытые свечи, без повторов, с грейсом."""

from __future__ import annotations

from decimal import Decimal

from exchanges.models import OHLCV
from paper.feed import PaperFeed


def _c(ts_ms: int) -> OHLCV:
    return OHLCV(
        timestamp=ts_ms,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("1"),
    )


class FakeAdapter:
    def __init__(self, candles: list[OHLCV]) -> None:
        self._all = sorted(candles, key=lambda c: c.timestamp)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[OHLCV]:
        out = [c for c in self._all if since is None or c.timestamp >= since]
        if limit is not None:
            out = out[:limit]
        return out


async def test_returns_only_closed_with_grace() -> None:
    tf_ms = 900_000  # 15m
    # три свечи: 0, 900, 1800; now=1900 → закрыты 0 и 900 (с grace 0); 1800 — нет
    candles = [_c(0), _c(900_000), _c(1_800_000)]
    now_ms = [1_900_000]
    feed = PaperFeed(
        adapter=FakeAdapter(candles),
        symbol="X/USDT:USDT",
        timeframe="15m",
        close_grace_ms=0,
        clock=lambda: now_ms[0],
    )
    # стартовое заполнение — отдаёт только последнюю закрытую (см. plan §invariant)
    out = await feed.fetch_new_closed(last_seen_ts=None)
    assert [c.timestamp for c in out] == [900_000]
    # теперь время прошло, 1800 закрылась
    now_ms[0] = 2_800_000
    out = await feed.fetch_new_closed(last_seen_ts=900_000)
    assert [c.timestamp for c in out] == [1_800_000]
    assert tf_ms > 0  # sanity


async def test_no_repeats() -> None:
    candles = [_c(0), _c(900_000)]
    feed = PaperFeed(
        adapter=FakeAdapter(candles),
        symbol="X/USDT:USDT",
        timeframe="15m",
        close_grace_ms=0,
        clock=lambda: 10_000_000,
    )
    first = await feed.fetch_new_closed(last_seen_ts=None)
    assert len(first) == 1
    # последующий вызов с last_seen_ts = последняя — ничего нового
    second = await feed.fetch_new_closed(last_seen_ts=first[-1].timestamp)
    assert second == []


async def test_grace_blocks_not_yet_closed() -> None:
    # tf=15m. Свеча 900_000 закроется в 1_800_000, grace 5000ms → не раньше 1_805_000.
    feed = PaperFeed(
        adapter=FakeAdapter([_c(900_000)]),
        symbol="X/USDT:USDT",
        timeframe="15m",
        close_grace_ms=5000,
        clock=lambda: 1_800_500,
    )
    out = await feed.fetch_new_closed(last_seen_ts=None)
    assert out == []


async def test_catches_up_multiple_missed() -> None:
    candles = [_c(i * 900_000) for i in range(1, 5)]  # 900k, 1800k, 2700k, 3600k
    feed = PaperFeed(
        adapter=FakeAdapter(candles),
        symbol="X/USDT:USDT",
        timeframe="15m",
        close_grace_ms=0,
        clock=lambda: 10_000_000,
    )
    out = await feed.fetch_new_closed(last_seen_ts=900_000)
    assert [c.timestamp for c in out] == [1_800_000, 2_700_000, 3_600_000]
