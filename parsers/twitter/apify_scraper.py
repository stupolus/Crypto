"""Apify Twitter Scraper interface — Protocol для DI.

Apify (https://apify.com) — платформа web scraping. Их Twitter Scraper
($50/мес Starter plan, 30K твитов/мес) polls указанные accounts и
возвращает свежие tweets через REST API.

Production: ApifyTwitterScraper (httpx wrapper). Тут — Protocol только.
"""

from __future__ import annotations

from typing import Any, Protocol


class ApifyScraperError(Exception):
    """Apify call failed."""


class ApifyTwitterScraper(Protocol):
    """Контракт реального scraper'а.

    fetch_recent(handles, since_ts_ms) → список raw tweet dicts.
    """

    async def fetch_recent(self, handles: list[str], since_ts_ms: int) -> list[dict[str, Any]]: ...
