"""FREDHttpFetcher — реальная имплементация FREDFetcher Protocol через httpx.

FRED API: https://fred.stlouisfed.org/docs/api/fred/
Auth: API key в query param `api_key`.

Endpoint: GET /fred/series/observations?series_id=DFF&api_key=...&sort_order=desc&limit=1
→ JSON {"observations": [{"date": "2026-05-13", "value": "5.33"}, ...]}

Получаем последнее observation для каждой series ID.
Sync interface (FREDFetcher Protocol) — внутри использует sync httpx.Client.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

import httpx

logger = logging.getLogger(__name__)

_FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
_TIMEOUT_S = 10.0


class FREDHttpFetcher:
    """Реальная имплементация FREDFetcher Protocol.

    Использование::

        fetcher = FREDHttpFetcher(api_key="abc123...")
        observations = fetcher.fetch_latest(["DFF", "UNRATE"])
        # → {"DFF": Decimal("5.33"), "UNRATE": Decimal("3.8")}

    Не raises на сетевых ошибках per-series — просто skip и не возвращает
    эту series в result. Caller (FREDAdapter) сам обрабатывает missing.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = _FRED_BASE_URL,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("FREDHttpFetcher requires non-empty api_key")
        self._api_key = api_key
        self._base_url = base_url
        self._client = client
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=_TIMEOUT_S)
        return self._client

    def fetch_latest(self, series_ids: list[str]) -> dict[str, Decimal]:
        client = self._get_client()
        result: dict[str, Decimal] = {}
        for sid in series_ids:
            try:
                resp = client.get(
                    self._base_url,
                    params={
                        "series_id": sid,
                        "api_key": self._api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": "1",
                    },
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.warning("FRED HTTP %s for %s: %s", e.response.status_code, sid, e)
                continue
            except Exception as e:
                logger.warning("FRED fetch %s failed: %s", sid, e)
                continue

            data = resp.json()
            observations = data.get("observations", [])
            if not observations:
                logger.info("FRED: no observations for %s", sid)
                continue

            value_str = observations[0].get("value")
            if value_str in (None, "", "."):  # FRED uses "." for missing
                logger.info("FRED: missing value for %s", sid)
                continue
            try:
                result[sid] = Decimal(value_str)
            except (InvalidOperation, TypeError):
                logger.warning("FRED: invalid value '%s' for %s", value_str, sid)

        return result
