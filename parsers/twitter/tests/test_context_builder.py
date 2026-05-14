"""Unit-тесты ``SentimentContextBuilder``.

Используем фейковый scraper + monkey-patched aggregator чтобы проверить
логику builder'а без реальных Apify / Groq вызовов.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from core.agents.evaluate import SentimentContextData
from parsers.twitter.aggregator import SentimentAggregator
from parsers.twitter.context_builder import SentimentContextBuilder
from parsers.twitter.models import SentimentSnapshot


class _StubScraper:
    """Минимальный fake ApifyTwitterScraper."""

    def __init__(self, tweets: list[dict[str, Any]] | None = None, raises: Exception | None = None):
        self._tweets = tweets or []
        self._raises = raises

    async def fetch_recent(self, handles: list[str], since_ts_ms: int) -> list[dict[str, Any]]:
        if self._raises is not None:
            raise self._raises
        return self._tweets


def _make_aggregator_with_snapshot(token: str, snapshot: SentimentSnapshot) -> SentimentAggregator:
    agg = AsyncMock(spec=SentimentAggregator)
    agg.aggregate.return_value = {token: snapshot}
    return cast(SentimentAggregator, agg)


def _make_aggregator_empty() -> SentimentAggregator:
    agg = AsyncMock(spec=SentimentAggregator)
    agg.aggregate.return_value = {}
    return cast(SentimentAggregator, agg)


def _valid_tweet_dict(idx: int = 0) -> dict[str, Any]:
    return {
        "tweet_id": f"tw{idx}",
        "author": "WuBlockchain",
        "text": f"BTC is mooning {idx}",
        "timestamp_ms": 1_700_000_000_000 + idx * 1000,
    }


@pytest.mark.asyncio
async def test_builder_returns_context_when_snapshot_present() -> None:
    scraper = _StubScraper(tweets=[_valid_tweet_dict(0), _valid_tweet_dict(1)])
    snapshot = SentimentSnapshot(
        token="BTC",
        window_start_ms=1_700_000_000_000,
        window_end_ms=1_700_003_600_000,
        tweet_count=2,
        avg_sentiment=Decimal("0.4"),
        breaking_count=0,
        high_relevance_count=1,
        sample_summaries=("bullish breakout", "OI rising"),
    )
    aggregator = _make_aggregator_with_snapshot("BTC", snapshot)

    builder = SentimentContextBuilder(
        scraper=scraper,
        aggregator=aggregator,
        handles=["WuBlockchain"],
        token="BTC",
    )
    ctx = await builder.build(now_ms=1_700_003_600_000)
    assert isinstance(ctx, SentimentContextData)
    assert ctx.twitter_sentiment_score == "0.4"
    parsed = json.loads(ctx.twitter_top_mentions)
    assert parsed == ["bullish breakout", "OI rising"]


@pytest.mark.asyncio
async def test_builder_returns_neutral_when_scraper_empty() -> None:
    scraper = _StubScraper(tweets=[])
    aggregator = _make_aggregator_empty()
    builder = SentimentContextBuilder(
        scraper=scraper, aggregator=aggregator, handles=["X"], token="BTC"
    )
    ctx = await builder.build(now_ms=1_700_000_000_000)
    assert ctx.twitter_sentiment_score == "0"
    assert ctx.twitter_top_mentions == "[]"


@pytest.mark.asyncio
async def test_builder_returns_neutral_when_scraper_raises() -> None:
    scraper = _StubScraper(raises=RuntimeError("apify 500"))
    aggregator = _make_aggregator_empty()
    builder = SentimentContextBuilder(
        scraper=scraper, aggregator=aggregator, handles=["X"], token="BTC"
    )
    ctx = await builder.build(now_ms=1_700_000_000_000)
    assert ctx.twitter_sentiment_score == "0"


@pytest.mark.asyncio
async def test_builder_returns_neutral_when_aggregator_raises() -> None:
    scraper = _StubScraper(tweets=[_valid_tweet_dict(0)])
    agg = AsyncMock(spec=SentimentAggregator)
    agg.aggregate.side_effect = RuntimeError("groq down")
    builder = SentimentContextBuilder(scraper=scraper, aggregator=agg, handles=["X"], token="BTC")
    ctx = await builder.build(now_ms=1_700_000_000_000)
    assert ctx.twitter_sentiment_score == "0"


@pytest.mark.asyncio
async def test_builder_returns_neutral_when_token_absent() -> None:
    """Aggregator вернул snapshots но не для нашего token → neutral."""
    scraper = _StubScraper(tweets=[_valid_tweet_dict(0)])
    snap = SentimentSnapshot(
        token="ETH",
        window_start_ms=1,
        window_end_ms=2,
        tweet_count=1,
        avg_sentiment=Decimal("0.5"),
    )
    agg = _make_aggregator_with_snapshot("ETH", snap)
    builder = SentimentContextBuilder(scraper=scraper, aggregator=agg, handles=["X"], token="BTC")
    ctx = await builder.build(now_ms=1_700_000_000_000)
    assert ctx.twitter_sentiment_score == "0"


@pytest.mark.asyncio
async def test_builder_caches_within_ttl() -> None:
    """Второй build в пределах TTL не должен дёргать scraper заново."""
    scraper = _StubScraper(tweets=[_valid_tweet_dict(0)])
    snap = SentimentSnapshot(
        token="BTC",
        window_start_ms=1,
        window_end_ms=2,
        tweet_count=1,
        avg_sentiment=Decimal("0.3"),
    )
    agg = _make_aggregator_with_snapshot("BTC", snap)
    builder = SentimentContextBuilder(
        scraper=scraper,
        aggregator=agg,
        handles=["X"],
        token="BTC",
        cache_ttl_s=60.0,
    )
    ctx1 = await builder.build(now_ms=1_700_000_000_000)
    ctx2 = await builder.build(now_ms=1_700_000_000_000 + 1000)
    # aggregator.aggregate должен быть вызван только один раз — второй из кеша
    aggregate_mock = cast(AsyncMock, agg).aggregate
    assert aggregate_mock.await_count == 1
    assert ctx1 is ctx2  # тот же объект из кеша


@pytest.mark.asyncio
async def test_builder_invalidate_cache_forces_refetch() -> None:
    scraper = _StubScraper(tweets=[_valid_tweet_dict(0)])
    snap = SentimentSnapshot(
        token="BTC",
        window_start_ms=1,
        window_end_ms=2,
        tweet_count=1,
        avg_sentiment=Decimal("0.3"),
    )
    agg = _make_aggregator_with_snapshot("BTC", snap)
    builder = SentimentContextBuilder(
        scraper=scraper, aggregator=agg, handles=["X"], token="BTC", cache_ttl_s=60.0
    )
    await builder.build(now_ms=1_700_000_000_000)
    builder.invalidate_cache()
    await builder.build(now_ms=1_700_000_000_000)
    aggregate_mock = cast(AsyncMock, agg).aggregate
    assert aggregate_mock.await_count == 2


def test_builder_rejects_empty_handles() -> None:
    scraper = _StubScraper()
    agg = _make_aggregator_empty()
    with pytest.raises(ValueError, match="handles"):
        SentimentContextBuilder(scraper=scraper, aggregator=agg, handles=[], token="BTC")


def test_builder_rejects_empty_token() -> None:
    scraper = _StubScraper()
    agg = _make_aggregator_empty()
    with pytest.raises(ValueError, match="token"):
        SentimentContextBuilder(scraper=scraper, aggregator=agg, handles=["X"], token="")


@pytest.mark.asyncio
async def test_builder_skips_invalid_tweets() -> None:
    """Невалидные tweet-словари не должны валить весь pipeline."""
    scraper = _StubScraper(
        tweets=[
            {"invalid": "no required fields"},
            _valid_tweet_dict(1),
        ]
    )
    snap = SentimentSnapshot(
        token="BTC",
        window_start_ms=1,
        window_end_ms=2,
        tweet_count=1,
        avg_sentiment=Decimal("0.1"),
    )
    agg = _make_aggregator_with_snapshot("BTC", snap)
    builder = SentimentContextBuilder(scraper=scraper, aggregator=agg, handles=["X"], token="BTC")
    ctx = await builder.build(now_ms=1_700_000_000_000)
    assert ctx.twitter_sentiment_score == "0.1"
    # aggregator получил один валидный tweet, не два
    aggregate_mock = cast(AsyncMock, agg).aggregate
    call_args = aggregate_mock.await_args
    assert call_args is not None
    sent_tweets = call_args.args[0]
    assert len(sent_tweets) == 1
