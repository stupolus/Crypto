"""Unit-тесты ``SentimentAggregator``."""

from __future__ import annotations

import pytest

from parsers.twitter import (
    SentimentAggregator,
    SentimentSnapshot,
    Tweet,
    TweetClassification,
)


class _FakeGroq:
    """Mock GroqClient — возвращает заданный ответ per-text."""

    def __init__(self, responses: dict[str, TweetClassification | Exception]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    async def classify_tweet(self, text: str) -> TweetClassification:
        self.calls.append(text)
        result = self._responses.get(text)
        if result is None:
            raise RuntimeError(f"unexpected text: {text!r}")
        if isinstance(result, Exception):
            raise result
        return result


def _tweet(tweet_id: str, text: str) -> Tweet:
    return Tweet(
        tweet_id=tweet_id,
        author="test_author",
        text=text,
        timestamp_ms=1_700_000_000_000,
    )


def _classification(
    sentiment: float,
    tokens: tuple[str, ...],
    relevance: str = "high",
    is_breaking: bool = False,
    summary: str = "test",
) -> TweetClassification:
    return TweetClassification(
        sentiment=sentiment,
        tokens=tokens,
        relevance=relevance,
        is_breaking=is_breaking,
        summary=summary,
    )


@pytest.mark.asyncio
async def test_aggregator_empty_input() -> None:
    groq = _FakeGroq({})
    agg = SentimentAggregator(groq)  # type: ignore[arg-type]
    result = await agg.aggregate([], window_start_ms=1, window_end_ms=2)
    assert result == {}


@pytest.mark.asyncio
async def test_aggregator_groups_by_token() -> None:
    groq = _FakeGroq(
        {
            "BTC pump": _classification(0.8, ("BTC",)),
            "ETH dump": _classification(-0.6, ("ETH",)),
            "BTC ETH news": _classification(0.2, ("BTC", "ETH")),
        }
    )
    agg = SentimentAggregator(groq)  # type: ignore[arg-type]
    tweets = [
        _tweet("1", "BTC pump"),
        _tweet("2", "ETH dump"),
        _tweet("3", "BTC ETH news"),
    ]
    result = await agg.aggregate(
        tweets, window_start_ms=1_700_000_000_000, window_end_ms=1_700_003_600_000
    )
    assert set(result.keys()) == {"BTC", "ETH"}
    btc = result["BTC"]
    assert isinstance(btc, SentimentSnapshot)
    assert btc.tweet_count == 2  # 2 tweets с BTC
    # avg(0.8, 0.2) = 0.5
    assert float(btc.avg_sentiment) == 0.5


@pytest.mark.asyncio
async def test_aggregator_filters_low_relevance() -> None:
    groq = _FakeGroq(
        {
            "high relevance": _classification(0.5, ("BTC",), relevance="high"),
            "noise tweet": _classification(0.9, ("BTC",), relevance="noise"),
            "low tweet": _classification(0.3, ("BTC",), relevance="low"),
        }
    )
    agg = SentimentAggregator(groq)  # type: ignore[arg-type]
    tweets = [
        _tweet("1", "high relevance"),
        _tweet("2", "noise tweet"),
        _tweet("3", "low tweet"),
    ]
    result = await agg.aggregate(tweets, window_start_ms=1, window_end_ms=2)
    # only the high-relevance one counted (medium тоже считается, но тут нет)
    assert "BTC" in result
    assert result["BTC"].tweet_count == 1
    assert float(result["BTC"].avg_sentiment) == 0.5


@pytest.mark.asyncio
async def test_aggregator_counts_breaking() -> None:
    groq = _FakeGroq(
        {
            "regular": _classification(0.5, ("BTC",), is_breaking=False),
            "BREAKING": _classification(0.7, ("BTC",), is_breaking=True),
            "BREAKING 2": _classification(0.8, ("BTC",), is_breaking=True),
        }
    )
    agg = SentimentAggregator(groq)  # type: ignore[arg-type]
    tweets = [
        _tweet("1", "regular"),
        _tweet("2", "BREAKING"),
        _tweet("3", "BREAKING 2"),
    ]
    result = await agg.aggregate(tweets, window_start_ms=1, window_end_ms=2)
    assert result["BTC"].breaking_count == 2


@pytest.mark.asyncio
async def test_aggregator_handles_groq_errors_gracefully() -> None:
    """Если Groq падает на одном tweet — остальные продолжают обрабатываться."""
    groq = _FakeGroq(
        {
            "ok": _classification(0.5, ("BTC",)),
            "fail": RuntimeError("Groq down"),
        }
    )
    agg = SentimentAggregator(groq)  # type: ignore[arg-type]
    tweets = [_tweet("1", "ok"), _tweet("2", "fail")]
    result = await agg.aggregate(tweets, window_start_ms=1, window_end_ms=2)
    assert "BTC" in result
    assert result["BTC"].tweet_count == 1


@pytest.mark.asyncio
async def test_aggregator_avg_sentiment_clamped() -> None:
    """avg_sentiment не выходит за [-1, 1]."""
    groq = _FakeGroq(
        {
            "very bullish": _classification(1.0, ("BTC",)),
            "very bullish 2": _classification(1.0, ("BTC",)),
        }
    )
    agg = SentimentAggregator(groq)  # type: ignore[arg-type]
    tweets = [_tweet("1", "very bullish"), _tweet("2", "very bullish 2")]
    result = await agg.aggregate(tweets, window_start_ms=1, window_end_ms=2)
    assert -1 <= float(result["BTC"].avg_sentiment) <= 1
