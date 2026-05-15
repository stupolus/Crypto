"""XApiScraper — реализация ``ApifyTwitterScraper`` Protocol через X API v2.

Альтернатива Apify ($50/мес fixed) — pay-per-use через официальный X API.
Bearer Token (App-only auth), simple httpx GET, без OAuth1 user context.

Endpoints используем:
- GET /2/users/by/username/{username} → user_id (один раз, cache'им)
- GET /2/users/{id}/tweets?start_time=ISO → recent tweets

Sentiment Layer 1 polls accounts каждые 15 минут. Если у тебя 20 handles
× 96 polls/день × 30 дней = 57,600 запросов/мес. Pay Per Use = ~$30-50/мес.

⚠ Free tier X API позволяет 1500 запросов/мес — этого не хватит.
Нужен **Basic** ($100/мес, 10K req) или **Pay Per Use** аккаунт.

Output формат tweet dict совпадает с Apify (так чтобы SentimentAggregator
обрабатывал одинаково):
- tweet_id, author, text, timestamp_ms,
- is_retweet, reply_count, retweet_count, like_count
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from parsers.twitter.apify_scraper import ApifyScraperError

logger = logging.getLogger(__name__)

_X_API_BASE = "https://api.twitter.com/2"
_DEFAULT_TIMEOUT_S = 15.0
_MAX_TWEETS_PER_REQUEST = 100  # X API max


class XApiScraper:
    """ApifyTwitterScraper Protocol через X API v2 (Bearer Token).

    Конструктор::

        scraper = XApiScraper(bearer_token="AAAAAA...")
        tweets = await scraper.fetch_recent(["VitalikButerin"], since_ts_ms=...)

    Кеш user_id для каждого handle живёт в памяти весь жизненный цикл
    instance — handles меняются редко, экономим запросы. На рестарте
    runner'а — заполняем заново.
    """

    def __init__(
        self,
        bearer_token: str,
        *,
        base_url: str = _X_API_BASE,
        client: httpx.AsyncClient | None = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> None:
        if not bearer_token:
            raise ValueError("XApiScraper: bearer_token required")
        self._bearer = bearer_token
        self._base_url = base_url
        self._client = client
        self._owns_client = client is None
        self._timeout_s = timeout_s
        self._user_id_cache: dict[str, str] = {}

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s)
        return self._client

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._bearer}",
            "Accept": "application/json",
        }

    async def _resolve_user_id(self, handle: str) -> str | None:
        """Get X user_id for a handle. Cached per-instance."""
        if handle in self._user_id_cache:
            return self._user_id_cache[handle]
        client = self._get_client()
        try:
            resp = await client.get(
                f"{self._base_url}/users/by/username/{handle}", headers=self._auth_headers()
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "X API user lookup HTTP %s for @%s: %s",
                e.response.status_code,
                handle,
                e,
            )
            return None
        except Exception as e:
            logger.warning("X API user lookup failed for @%s: %s", handle, e)
            return None

        try:
            data = resp.json()
        except ValueError:
            return None
        user_id = data.get("data", {}).get("id") if isinstance(data, dict) else None
        if isinstance(user_id, str) and user_id:
            self._user_id_cache[handle] = user_id
            return user_id
        return None

    async def _fetch_user_tweets(
        self, user_id: str, handle: str, since_ts_ms: int
    ) -> list[dict[str, Any]]:
        """One handle's tweets. Returns list[tweet_dict in Apify format]."""
        client = self._get_client()
        start_time = datetime.fromtimestamp(since_ts_ms / 1000, tz=UTC).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        params: dict[str, str] = {
            "max_results": str(_MAX_TWEETS_PER_REQUEST),
            "start_time": start_time,
            "tweet.fields": "created_at,public_metrics,referenced_tweets",
        }
        try:
            resp = await client.get(
                f"{self._base_url}/users/{user_id}/tweets",
                params=params,
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "X API tweets HTTP %s for @%s: %s",
                e.response.status_code,
                handle,
                e,
            )
            return []
        except Exception as e:
            logger.warning("X API tweets fetch failed for @%s: %s", handle, e)
            return []

        try:
            data = resp.json()
        except ValueError:
            return []

        if not isinstance(data, dict):
            return []
        tweets_raw = data.get("data", [])
        if not isinstance(tweets_raw, list):
            return []

        return [_normalize_tweet(t, handle) for t in tweets_raw if isinstance(t, dict)]

    async def fetch_recent(self, handles: list[str], since_ts_ms: int) -> list[dict[str, Any]]:
        """Fetch tweets от всех handles параллельно (asyncio.gather).

        Если конкретный handle падает (404, rate-limit) — пропускаем,
        не валим весь батч (compatible with Apify behavior).
        """
        if not handles:
            return []
        if since_ts_ms <= 0:
            raise ApifyScraperError("XApiScraper: since_ts_ms must be > 0")

        # Resolve user ids in parallel (cached)
        ids = await asyncio.gather(*[self._resolve_user_id(h) for h in handles])
        # Fetch each handle's tweets in parallel
        tasks = [
            self._fetch_user_tweets(user_id, handle, since_ts_ms)
            for handle, user_id in zip(handles, ids, strict=False)
            if user_id is not None
        ]
        if not tasks:
            return []
        batches = await asyncio.gather(*tasks, return_exceptions=False)
        result: list[dict[str, Any]] = []
        for batch in batches:
            result.extend(batch)
        return result


def _normalize_tweet(raw: dict[str, Any], handle: str) -> dict[str, Any]:
    """X API tweet → Apify-compatible dict.

    Sentiment pipeline ждёт {tweet_id, author, text, timestamp_ms,
    is_retweet, reply_count, retweet_count, like_count}.
    """
    metrics = raw.get("public_metrics", {}) or {}
    referenced = raw.get("referenced_tweets") or []
    is_retweet = any(isinstance(ref, dict) and ref.get("type") == "retweeted" for ref in referenced)
    created_at_iso = raw.get("created_at", "")
    timestamp_ms = _parse_iso_ms(created_at_iso)
    return {
        "tweet_id": str(raw.get("id", "")),
        "author": handle,
        "text": str(raw.get("text", "")),
        "timestamp_ms": timestamp_ms,
        "is_retweet": is_retweet,
        "reply_count": int(metrics.get("reply_count", 0) or 0),
        "retweet_count": int(metrics.get("retweet_count", 0) or 0),
        "like_count": int(metrics.get("like_count", 0) or 0),
    }


def _parse_iso_ms(iso: str) -> int:
    if not iso:
        return 0
    try:
        # X API формат: '2025-05-14T12:34:56.000Z' или '2025-05-14T12:34:56Z'
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError):
        return 0
