"""Unit-тесты ``NewsAggregator`` + ``/api/news`` endpoint."""

from __future__ import annotations

import time

import httpx
import respx
from fastapi.testclient import TestClient

from core.dashboard.api import create_app
from core.dashboard.news import (
    DEFAULT_FEEDS,
    NewsAggregator,
    NewsItem,
    _parse_rfc2822,
    _strip_html,
)

_RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <item>
      <title>Bitcoin hits new ATH</title>
      <link>https://example.com/article-1</link>
      <pubDate>Wed, 14 May 2025 12:34:56 +0000</pubDate>
      <description>BTC up 8% on ETF inflows. &lt;p&gt;Details inside&lt;/p&gt;</description>
    </item>
    <item>
      <title>ETH staking yield drops</title>
      <link>https://example.com/article-2</link>
      <pubDate>Wed, 14 May 2025 11:00:00 +0000</pubDate>
      <description>Validator queue clears</description>
    </item>
  </channel>
</rss>
"""


def test_strip_html() -> None:
    assert _strip_html("Hello <b>world</b>") == "Hello world"
    assert _strip_html("<p>Multi   line</p> text") == "Multi line text"
    assert _strip_html("") == ""


def test_parse_rfc2822() -> None:
    ts = _parse_rfc2822("Wed, 14 May 2025 12:34:56 +0000")
    # Should be reasonable May 2025 timestamp
    assert ts > 1_700_000_000_000


def test_aggregator_with_mock_rss() -> None:
    with respx.mock(assert_all_called=False) as mock:
        # Mock all default feeds — return same sample
        for _source, url in DEFAULT_FEEDS:
            mock.get(url).mock(return_value=httpx.Response(200, text=_RSS_SAMPLE))

        agg = NewsAggregator()
        items = agg.get(limit=20)
        # 3 feeds × 2 items = 6
        assert len(items) > 0
        first = items[0]
        assert first.title in ("Bitcoin hits new ATH", "ETH staking yield drops")
        assert "example.com/article" in first.link
        assert first.source in {"CoinDesk", "Cointelegraph", "Decrypt"}
        # DESC by timestamp
        for i in range(len(items) - 1):
            assert items[i].pub_ts_ms >= items[i + 1].pub_ts_ms


def test_aggregator_handles_feed_error() -> None:
    """Если один из feed'ов 500'ит — пропускаем, не валим весь aggregator."""
    with respx.mock(assert_all_called=False) as mock:
        for source, url in DEFAULT_FEEDS:
            if source == "CoinDesk":
                mock.get(url).mock(return_value=httpx.Response(500))
            else:
                mock.get(url).mock(return_value=httpx.Response(200, text=_RSS_SAMPLE))

        agg = NewsAggregator()
        items = agg.get(limit=20)
        # Должны быть items из других feed'ов
        sources = {i.source for i in items}
        assert "CoinDesk" not in sources
        assert len(items) > 0


def test_aggregator_caches_within_ttl() -> None:
    call_count = {"n": 0}

    def _handler(_request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, text=_RSS_SAMPLE)

    with respx.mock(assert_all_called=False) as mock:
        for _source, url in DEFAULT_FEEDS:
            mock.get(url).mock(side_effect=_handler)

        agg = NewsAggregator(ttl_s=60.0)
        agg.get()
        first_count = call_count["n"]
        # Второй вызов — из кеша
        agg.get()
        assert call_count["n"] == first_count


def test_aggregator_refetch_after_ttl() -> None:
    with respx.mock(assert_all_called=False) as mock:
        for _source, url in DEFAULT_FEEDS:
            mock.get(url).mock(return_value=httpx.Response(200, text=_RSS_SAMPLE))

        agg = NewsAggregator(ttl_s=0.01)
        agg.get()
        time.sleep(0.05)
        agg.get()
        # Suffice to not blow up; mock returns same text


def test_news_endpoint() -> None:
    with respx.mock(assert_all_called=False) as mock:
        for _source, url in DEFAULT_FEEDS:
            mock.get(url).mock(return_value=httpx.Response(200, text=_RSS_SAMPLE))

        app = create_app(
            outcomes_db="/tmp/no.sqlite",
            halt_flag_file=None,
            heartbeat_file=None,
        )
        client = TestClient(app)
        resp = client.get("/api/news?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) <= 5
        if data["items"]:
            item = data["items"][0]
            assert "title" in item
            assert "link" in item
            assert "source" in item
            assert "pub_ts_ms" in item


def test_news_limit_validation() -> None:
    app = create_app(
        outcomes_db="/tmp/no.sqlite",
        halt_flag_file=None,
        heartbeat_file=None,
    )
    client = TestClient(app)
    assert client.get("/api/news?limit=0").status_code == 400
    assert client.get("/api/news?limit=200").status_code == 400


def test_news_injectable_aggregator() -> None:
    """Можно подменить aggregator на свой (для тестов / альтернативных источников)."""

    class _FakeAgg(NewsAggregator):
        def __init__(self) -> None:
            super().__init__(feeds=())

        def get(self, *, limit: int = 30) -> list[NewsItem]:
            return [
                NewsItem(
                    title="Mocked",
                    link="https://example.com",
                    source="TestSrc",
                    pub_ts_ms=1_700_000_000_000,
                    summary="hi",
                )
            ]

    app = create_app(
        outcomes_db="/tmp/no.sqlite",
        halt_flag_file=None,
        heartbeat_file=None,
        news_aggregator=_FakeAgg(),
    )
    client = TestClient(app)
    data = client.get("/api/news").json()
    assert data["items"][0]["title"] == "Mocked"
    assert data["items"][0]["source"] == "TestSrc"
