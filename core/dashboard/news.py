"""News feed для дашборда — RSS aggregator с in-memory TTL cache.

Без auth ключей: используем публичные RSS-ленты crypto/macro новостей.
Один TTL-кеш на всех клиентов API (5 минут) — не давим источники.

Источники (default, можно override через env):
- CoinDesk RSS
- Cointelegraph RSS
- (опционально) Decrypt, The Block

Каждый item: title, link, source, pub_ts_ms, summary (короткий).
Если RSS-сервер недоступен — просто пропускаем (degrade gracefully).

В production будущее: добавить Twitter feed (когда подключим Apify) —
там же сложить через те же модели.
"""

from __future__ import annotations

import email.utils
import logging
import re
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

DEFAULT_FEEDS: tuple[tuple[str, str], ...] = (
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Decrypt", "https://decrypt.co/feed"),
)

_TTL_S = 300.0  # 5 минут
_FETCH_TIMEOUT_S = 8.0
_MAX_ITEMS_PER_FEED = 12


@dataclass(frozen=True)
class NewsItem:
    title: str
    link: str
    source: str
    pub_ts_ms: int
    summary: str


@dataclass
class _CacheEntry:
    items: list[NewsItem]
    fetched_at_ts: float


class NewsAggregator:
    """In-memory RSS aggregator с TTL cache, thread-safe.

    Singleton-style использование: один экземпляр на app, читается из
    нескольких HTTP requests одновременно (threadsafe lock).
    """

    def __init__(
        self,
        feeds: Iterable[tuple[str, str]] = DEFAULT_FEEDS,
        *,
        ttl_s: float = _TTL_S,
        fetch_timeout_s: float = _FETCH_TIMEOUT_S,
    ) -> None:
        self._feeds = list(feeds)
        self._ttl_s = ttl_s
        self._fetch_timeout_s = fetch_timeout_s
        self._cache: _CacheEntry | None = None
        self._lock = threading.Lock()

    def get(self, *, limit: int = 30) -> list[NewsItem]:
        """Получить latest news. Если кеш свежий — возвращаем его."""
        with self._lock:
            if self._cache is not None and time.time() - self._cache.fetched_at_ts < self._ttl_s:
                return self._cache.items[:limit]
            items = self._fetch_all()
            self._cache = _CacheEntry(items=items, fetched_at_ts=time.time())
            return items[:limit]

    def _fetch_all(self) -> list[NewsItem]:
        all_items: list[NewsItem] = []
        with httpx.Client(timeout=self._fetch_timeout_s, follow_redirects=True) as client:
            for source, url in self._feeds:
                try:
                    resp = client.get(url, headers={"User-Agent": "crypto-dashboard/1.0"})
                    resp.raise_for_status()
                    parsed = _parse_rss(resp.text, source=source)
                    all_items.extend(parsed[:_MAX_ITEMS_PER_FEED])
                    logger.debug("news: %s → %d items", source, len(parsed))
                except Exception as exc:
                    logger.warning("news fetch failed %s: %s", source, exc)
                    continue
        # Sort DESC by pub_ts
        all_items.sort(key=lambda x: x.pub_ts_ms, reverse=True)
        return all_items


def _parse_rss(xml_text: str, *, source: str) -> list[NewsItem]:
    """Парсим RSS 2.0 / Atom XML → list[NewsItem]."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    items: list[NewsItem] = []
    # RSS 2.0: <rss><channel><item>...
    for item in root.iter("item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        pub = _text(item.find("pubDate"))
        description = _text(item.find("description"))
        if not title or not link:
            continue
        ts_ms = _parse_rfc2822(pub) if pub else int(time.time() * 1000)
        items.append(
            NewsItem(
                title=_strip_html(title),
                link=link,
                source=source,
                pub_ts_ms=ts_ms,
                summary=_strip_html(description)[:240],
            )
        )

    # Atom: <feed><entry>...
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
            title = _text(entry.find("a:title", ns))
            link_el = entry.find("a:link", ns)
            link = (link_el.get("href") or "") if link_el is not None else ""
            pub = _text(entry.find("a:updated", ns)) or _text(entry.find("a:published", ns))
            summary = _text(entry.find("a:summary", ns))
            if not title or not link:
                continue
            ts_ms = _parse_iso(pub) if pub else int(time.time() * 1000)
            items.append(
                NewsItem(
                    title=_strip_html(title),
                    link=link,
                    source=source,
                    pub_ts_ms=ts_ms,
                    summary=_strip_html(summary)[:240],
                )
            )

    return items


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(s: str) -> str:
    if not s:
        return ""
    no_tags = _HTML_TAG_RE.sub("", s)
    return _WS_RE.sub(" ", no_tags).strip()


def _parse_rfc2822(s: str) -> int:
    """RSS pubDate: 'Wed, 14 May 2025 12:34:56 +0000' → ts_ms."""
    try:
        dt = email.utils.parsedate_to_datetime(s)
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError):
        return int(time.time() * 1000)


def _parse_iso(s: str) -> int:
    """Atom updated: '2025-05-14T12:34:56Z' → ts_ms."""
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError):
        return int(time.time() * 1000)


def news_item_to_dict(item: NewsItem) -> dict[str, str | int]:
    return {
        "title": item.title,
        "link": item.link,
        "source": item.source,
        "pub_ts_ms": item.pub_ts_ms,
        "summary": item.summary,
    }
