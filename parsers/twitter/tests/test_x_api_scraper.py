"""Unit-тесты ``XApiScraper`` — респонс X API v2 mock через respx."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from parsers.twitter.apify_scraper import ApifyScraperError
from parsers.twitter.x_api_scraper import XApiScraper


def _user_resp(user_id: str = "12345", username: str = "VitalikButerin") -> dict[str, Any]:
    return {"data": {"id": user_id, "name": "Vitalik", "username": username}}


def _tweets_resp(tweets: list[dict[str, Any]]) -> dict[str, Any]:
    return {"data": tweets, "meta": {"result_count": len(tweets)}}


def _tweet_item(
    tweet_id: str = "1700000001",
    text: str = "BTC to the moon",
    created_at: str = "2025-05-14T12:00:00.000Z",
    is_retweet: bool = False,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": tweet_id,
        "text": text,
        "created_at": created_at,
        "public_metrics": {
            "retweet_count": 5,
            "reply_count": 3,
            "like_count": 42,
            "quote_count": 1,
        },
    }
    if is_retweet:
        item["referenced_tweets"] = [{"type": "retweeted", "id": "1699999999"}]
    return item


def test_bearer_token_required() -> None:
    with pytest.raises(ValueError, match="bearer_token required"):
        XApiScraper("")


@pytest.mark.asyncio
async def test_fetch_recent_single_handle() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.twitter.com/2") as mock:
            mock.get("/users/by/username/VitalikButerin").mock(
                return_value=httpx.Response(200, json=_user_resp("99", "VitalikButerin"))
            )
            mock.get("/users/99/tweets").mock(
                return_value=httpx.Response(
                    200, json=_tweets_resp([_tweet_item("100", "ETH update")])
                )
            )
            scraper = XApiScraper("test-bearer", client=client)
            tweets = await scraper.fetch_recent(["VitalikButerin"], since_ts_ms=1_700_000_000_000)

    assert len(tweets) == 1
    t = tweets[0]
    assert t["tweet_id"] == "100"
    assert t["author"] == "VitalikButerin"
    assert t["text"] == "ETH update"
    assert t["timestamp_ms"] > 0
    assert t["is_retweet"] is False
    assert t["like_count"] == 42
    assert t["retweet_count"] == 5


@pytest.mark.asyncio
async def test_fetch_recent_multiple_handles_parallel() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.twitter.com/2") as mock:
            mock.get("/users/by/username/alice").mock(
                return_value=httpx.Response(200, json=_user_resp("1", "alice"))
            )
            mock.get("/users/by/username/bob").mock(
                return_value=httpx.Response(200, json=_user_resp("2", "bob"))
            )
            mock.get("/users/1/tweets").mock(
                return_value=httpx.Response(200, json=_tweets_resp([_tweet_item("a1")]))
            )
            mock.get("/users/2/tweets").mock(
                return_value=httpx.Response(200, json=_tweets_resp([_tweet_item("b1")]))
            )

            scraper = XApiScraper("test", client=client)
            tweets = await scraper.fetch_recent(["alice", "bob"], since_ts_ms=1_700_000_000_000)

    assert len(tweets) == 2
    assert {t["author"] for t in tweets} == {"alice", "bob"}


@pytest.mark.asyncio
async def test_fetch_recent_caches_user_id() -> None:
    """Повторный вызов на тот же handle не делает 2-й lookup."""
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.twitter.com/2") as mock:
            user_route = mock.get("/users/by/username/alice").mock(
                return_value=httpx.Response(200, json=_user_resp("1", "alice"))
            )
            mock.get("/users/1/tweets").mock(
                return_value=httpx.Response(200, json=_tweets_resp([_tweet_item("a1")]))
            )

            scraper = XApiScraper("test", client=client)
            await scraper.fetch_recent(["alice"], since_ts_ms=1_700_000_000_000)
            await scraper.fetch_recent(["alice"], since_ts_ms=1_700_000_500_000)

            assert user_route.call_count == 1  # cached


@pytest.mark.asyncio
async def test_handles_unknown_username_gracefully() -> None:
    """Если X API возвращает 404 на user lookup — пропускаем handle."""
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.twitter.com/2") as mock:
            mock.get("/users/by/username/badhandle").mock(
                return_value=httpx.Response(404, json={"title": "Not Found"})
            )
            mock.get("/users/by/username/alice").mock(
                return_value=httpx.Response(200, json=_user_resp("1", "alice"))
            )
            mock.get("/users/1/tweets").mock(
                return_value=httpx.Response(200, json=_tweets_resp([_tweet_item("a1")]))
            )

            scraper = XApiScraper("test", client=client)
            tweets = await scraper.fetch_recent(
                ["badhandle", "alice"], since_ts_ms=1_700_000_000_000
            )

    # badhandle пропущен, alice осталась
    assert len(tweets) == 1
    assert tweets[0]["author"] == "alice"


@pytest.mark.asyncio
async def test_handles_rate_limited_tweets() -> None:
    """429 на tweets endpoint → empty list для этого handle."""
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.twitter.com/2") as mock:
            mock.get("/users/by/username/alice").mock(
                return_value=httpx.Response(200, json=_user_resp("1", "alice"))
            )
            mock.get("/users/1/tweets").mock(
                return_value=httpx.Response(429, json={"title": "Too Many Requests"})
            )

            scraper = XApiScraper("test", client=client)
            tweets = await scraper.fetch_recent(["alice"], since_ts_ms=1_700_000_000_000)

    assert tweets == []


@pytest.mark.asyncio
async def test_fetch_recent_empty_handles() -> None:
    scraper = XApiScraper("test")
    assert await scraper.fetch_recent([], since_ts_ms=1_700_000_000_000) == []


@pytest.mark.asyncio
async def test_fetch_recent_negative_since_rejected() -> None:
    scraper = XApiScraper("test")
    with pytest.raises(ApifyScraperError, match="since_ts_ms"):
        await scraper.fetch_recent(["alice"], since_ts_ms=0)


@pytest.mark.asyncio
async def test_retweet_detection() -> None:
    """referenced_tweets[type=retweeted] → is_retweet=True."""
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.twitter.com/2") as mock:
            mock.get("/users/by/username/alice").mock(
                return_value=httpx.Response(200, json=_user_resp("1", "alice"))
            )
            mock.get("/users/1/tweets").mock(
                return_value=httpx.Response(
                    200,
                    json=_tweets_resp(
                        [
                            _tweet_item("a1", "original"),
                            _tweet_item("a2", "RT @x: copy", is_retweet=True),
                        ]
                    ),
                )
            )
            scraper = XApiScraper("test", client=client)
            tweets = await scraper.fetch_recent(["alice"], since_ts_ms=1_700_000_000_000)

    by_id = {t["tweet_id"]: t for t in tweets}
    assert by_id["a1"]["is_retweet"] is False
    assert by_id["a2"]["is_retweet"] is True


@pytest.mark.asyncio
async def test_authorization_header_sent() -> None:
    async with httpx.AsyncClient() as client:
        with respx.mock(base_url="https://api.twitter.com/2") as mock:
            user_route = mock.get("/users/by/username/alice").mock(
                return_value=httpx.Response(200, json=_user_resp("1", "alice"))
            )
            mock.get("/users/1/tweets").mock(
                return_value=httpx.Response(200, json=_tweets_resp([]))
            )

            scraper = XApiScraper("MY_BEARER_42", client=client)
            await scraper.fetch_recent(["alice"], since_ts_ms=1_700_000_000_000)

    auth = user_route.calls.last.request.headers.get("authorization", "")
    assert auth == "Bearer MY_BEARER_42"
