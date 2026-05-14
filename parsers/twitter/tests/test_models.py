"""Unit-тесты ``parsers.twitter.models``."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from parsers.twitter import SentimentSnapshot, Tweet


def test_tweet_basic() -> None:
    t = Tweet(
        tweet_id="1234567890",
        author="VitalikButerin",
        text="ETH gas fees are too high",
        timestamp_ms=1_700_000_000_000,
    )
    assert t.author == "VitalikButerin"
    assert t.is_retweet is False


def test_tweet_with_engagement() -> None:
    t = Tweet(
        tweet_id="9876",
        author="cz_binance",
        text="...",
        timestamp_ms=1_700_000_000_000,
        like_count=15_000,
        retweet_count=3_000,
        reply_count=500,
    )
    assert t.like_count == 15_000


def test_tweet_immutable() -> None:
    t = Tweet(tweet_id="1", author="x", text="t", timestamp_ms=1_700_000_000_000)
    with pytest.raises(ValidationError):
        t.text = "modified"  # type: ignore[misc]


def test_tweet_validation() -> None:
    with pytest.raises(ValidationError):
        Tweet(tweet_id="", author="x", text="t", timestamp_ms=1_700_000_000_000)
    with pytest.raises(ValidationError):
        Tweet(tweet_id="1", author="x", text="t", timestamp_ms=-1)
    with pytest.raises(ValidationError):
        Tweet(
            tweet_id="1",
            author="x",
            text="t",
            timestamp_ms=1_700_000_000_000,
            like_count=-1,
        )


def test_sentiment_snapshot_basic() -> None:
    s = SentimentSnapshot(
        token="BTC",
        window_start_ms=1_700_000_000_000,
        window_end_ms=1_700_003_600_000,
        tweet_count=10,
        avg_sentiment=Decimal("0.5"),
    )
    assert s.token == "BTC"
    assert s.avg_sentiment == Decimal("0.5")
    assert s.breaking_count == 0


def test_sentiment_snapshot_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        SentimentSnapshot(
            token="BTC",
            window_start_ms=1_700_000_000_000,
            window_end_ms=1_700_003_600_000,
            tweet_count=10,
            avg_sentiment=Decimal("1.5"),
        )
    with pytest.raises(ValidationError):
        SentimentSnapshot(
            token="BTC",
            window_start_ms=1_700_000_000_000,
            window_end_ms=1_700_003_600_000,
            tweet_count=10,
            avg_sentiment=Decimal("-2"),
        )
