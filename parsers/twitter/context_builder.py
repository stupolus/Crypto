"""SentimentContextBuilder — SentimentSnapshot per token → SentimentContextData.

Связывает Layer 1 (Twitter pipeline: Apify + Groq + Aggregator) и Layer 3
(Sentiment Analyst). Используется в hot loop: builder вызывается перед
``evaluate_with_team``, возвращает готовый ``SentimentContextData``.

Embedded cache на ``cache_ttl_s`` секунд (по умолчанию 5 минут) — sentiment
обновляется чаще macro, но дёргать Apify+Groq на каждый Layer 2 сигнал
расточительно.

Если scraper или aggregator падают → builder возвращает нейтральные
defaults (``"0"`` / ``"[]"``) и предупреждение в логи. Layer 3 промпт
обрабатывает этот плейсхолдер.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass

from core.agents.evaluate import SentimentContextData
from parsers.twitter.aggregator import SentimentAggregator
from parsers.twitter.apify_scraper import ApifyTwitterScraper
from parsers.twitter.models import SentimentSnapshot, Tweet

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_TTL_S = 300.0  # 5 минут
_DEFAULT_LOOKBACK_MS = 60 * 60 * 1000  # 1 час
_DEFAULT_MAX_SUMMARIES = 5


@dataclass
class _CacheEntry:
    snapshot: SentimentContextData
    fetched_at_ts: float


class SentimentContextBuilder:
    """Объединяет Apify scraper + Groq aggregator в один SentimentContextData.

    DI обоих компонентов через конструктор. Кеш на ``cache_ttl_s`` секунд.

    Использование::

        builder = SentimentContextBuilder(
            scraper=apify, aggregator=agg, handles=["WuBlockchain"], token="BTC"
        )
        ctx = await builder.build(now_ms=int(time.time()*1000))
        decision = await evaluate_with_team(..., sentiment_data=ctx)
    """

    def __init__(
        self,
        *,
        scraper: ApifyTwitterScraper,
        aggregator: SentimentAggregator,
        handles: Sequence[str],
        token: str,
        cache_ttl_s: float = _DEFAULT_CACHE_TTL_S,
        lookback_ms: int = _DEFAULT_LOOKBACK_MS,
        max_summaries: int = _DEFAULT_MAX_SUMMARIES,
    ) -> None:
        if not handles:
            raise ValueError("SentimentContextBuilder: handles must be non-empty")
        if not token:
            raise ValueError("SentimentContextBuilder: token must be non-empty")
        self._scraper = scraper
        self._aggregator = aggregator
        self._handles = list(handles)
        self._token = token
        self._cache_ttl_s = cache_ttl_s
        self._lookback_ms = lookback_ms
        self._max_summaries = max_summaries
        self._cache: _CacheEntry | None = None

    async def build(self, *, now_ms: int) -> SentimentContextData:
        """Собрать SentimentContextData. Кешируется на cache_ttl_s."""
        now = time.monotonic()
        if self._cache is not None and now - self._cache.fetched_at_ts < self._cache_ttl_s:
            return self._cache.snapshot

        ctx = await self._build_fresh(now_ms=now_ms)
        self._cache = _CacheEntry(snapshot=ctx, fetched_at_ts=now)
        return ctx

    async def _build_fresh(self, *, now_ms: int) -> SentimentContextData:
        since_ms = now_ms - self._lookback_ms
        try:
            raw_tweets = await self._scraper.fetch_recent(self._handles, since_ms)
        except Exception as e:
            logger.warning("SentimentContextBuilder scraper failed: %s", e)
            return self._neutral_context()

        if not raw_tweets:
            logger.debug("SentimentContextBuilder: no tweets in window")
            return self._neutral_context()

        tweets = _parse_tweets(raw_tweets)
        if not tweets:
            return self._neutral_context()

        try:
            by_token = await self._aggregator.aggregate(
                tweets, window_start_ms=since_ms, window_end_ms=now_ms
            )
        except Exception as e:
            logger.warning("SentimentContextBuilder aggregator failed: %s", e)
            return self._neutral_context()

        snapshot = by_token.get(self._token)
        if snapshot is None:
            return self._neutral_context()

        return self._snapshot_to_context(snapshot)

    def _snapshot_to_context(self, snapshot: SentimentSnapshot) -> SentimentContextData:
        top_mentions = json.dumps(
            list(snapshot.sample_summaries[: self._max_summaries]),
            ensure_ascii=False,
        )
        return SentimentContextData(
            twitter_sentiment_score=str(snapshot.avg_sentiment),
            twitter_top_mentions=top_mentions,
            news_headlines="[]",  # отдельный источник, отложено
            funding_rate="0",  # дополнит MarketContextBuilder
            tg_channels_summary="neutral",  # тоже отдельно
        )

    @staticmethod
    def _neutral_context() -> SentimentContextData:
        return SentimentContextData()

    def invalidate_cache(self) -> None:
        """Принудительный сброс кеша. Для тестов / breaking events."""
        self._cache = None


def _parse_tweets(raw: list[dict[str, object]]) -> list[Tweet]:
    """Конвертирует raw dict-ы из Apify в Tweet pydantic-модели.

    Невалидные записи пропускаются с warning.
    """
    parsed: list[Tweet] = []
    for item in raw:
        try:
            parsed.append(Tweet.model_validate(item))
        except Exception as e:
            logger.debug("SentimentContextBuilder: skip invalid tweet %r: %s", item, e)
    return parsed
