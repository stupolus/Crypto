"""SentimentAggregator — превращает tweets в SentimentSnapshot per token.

Pipeline:
1. ApifyTwitterScraper отдаёт raw tweets (батчем)
2. SentimentAggregator классифицирует каждый через GroqClient (параллельно)
3. Группирует по token → SentimentSnapshot per token
4. SentimentAnalystAgent (Layer 3) использует snapshots

Низкая relevance/noise игнорируется. is_breaking считается отдельно.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING

from parsers.twitter.models import SentimentSnapshot, Tweet

if TYPE_CHECKING:
    from parsers.twitter.groq_client import GroqClient, TweetClassification

logger = logging.getLogger(__name__)


class SentimentAggregator:
    """Классифицирует tweets через Groq и агрегирует в SentimentSnapshot.

    Сценарий использования::

        aggregator = SentimentAggregator(groq_client)
        snapshots = await aggregator.aggregate(
            tweets, window_start_ms=..., window_end_ms=...
        )
        # → dict[token, SentimentSnapshot]
    """

    def __init__(
        self,
        groq_client: GroqClient,
        *,
        max_concurrent: int = 5,
        relevance_threshold: tuple[str, ...] = ("high", "medium"),
        max_summaries_per_token: int = 3,
    ) -> None:
        self._groq = groq_client
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._relevance_threshold = set(relevance_threshold)
        self._max_summaries = max_summaries_per_token

    async def _classify_one(self, tweet: Tweet) -> tuple[Tweet, TweetClassification | None]:
        async with self._semaphore:
            try:
                result = await self._groq.classify_tweet(tweet.text)
            except Exception as e:
                logger.warning("groq classify failed for tweet %s: %s", tweet.tweet_id, e)
                return tweet, None
        return tweet, result

    async def aggregate(
        self,
        tweets: list[Tweet],
        *,
        window_start_ms: int,
        window_end_ms: int,
    ) -> dict[str, SentimentSnapshot]:
        """Классифицирует и группирует.

        Returns mapping {token: SentimentSnapshot}. Только tokens с
        ≥1 relevant tweet попадают в результат.
        """
        if not tweets:
            return {}

        results = await asyncio.gather(*[self._classify_one(t) for t in tweets])

        by_token: dict[str, list[tuple[Tweet, TweetClassification]]] = defaultdict(list)
        for tweet, classification in results:
            if classification is None:
                continue
            if classification.relevance not in self._relevance_threshold:
                continue
            for token in classification.tokens:
                by_token[token].append((tweet, classification))

        snapshots: dict[str, SentimentSnapshot] = {}
        for token, items in by_token.items():
            sentiments = [Decimal(str(c.sentiment)) for _, c in items]
            avg = sum(sentiments) / Decimal(len(sentiments))
            avg = avg.quantize(Decimal("0.001"))
            avg = max(Decimal("-1"), min(Decimal("1"), avg))

            breaking_count = sum(1 for _, c in items if c.is_breaking)
            high_count = sum(1 for _, c in items if c.relevance == "high")

            summaries = tuple(c.summary for _, c in items[: self._max_summaries])

            snapshots[token] = SentimentSnapshot(
                token=token,
                window_start_ms=window_start_ms,
                window_end_ms=window_end_ms,
                tweet_count=len(items),
                avg_sentiment=avg,
                breaking_count=breaking_count,
                high_relevance_count=high_count,
                sample_summaries=summaries,
            )
        return snapshots
