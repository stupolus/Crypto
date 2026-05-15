"""Pydantic-модели Twitter pipeline."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class Tweet(BaseModel):
    """Один tweet от Apify Twitter Scraper.

    Минимальные поля чтобы передавать в Groq classifier.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    tweet_id: str = Field(min_length=1)
    author: str = Field(min_length=1, description="Twitter handle, e.g. 'VitalikButerin'")
    text: str = Field(min_length=1)
    timestamp_ms: int = Field(gt=0)
    is_retweet: bool = False
    reply_count: int = Field(default=0, ge=0)
    retweet_count: int = Field(default=0, ge=0)
    like_count: int = Field(default=0, ge=0)


class SentimentSnapshot(BaseModel):
    """Агрегированный sentiment по одному символу за временное окно.

    Output aggregator'а → input Sentiment Analyst Layer 3.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    token: str = Field(min_length=1, description="Например 'BTC'")
    window_start_ms: int = Field(gt=0)
    window_end_ms: int = Field(gt=0)
    tweet_count: int = Field(ge=0)
    avg_sentiment: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    breaking_count: int = Field(default=0, ge=0)
    high_relevance_count: int = Field(default=0, ge=0)
    sample_summaries: tuple[str, ...] = Field(default_factory=tuple)
