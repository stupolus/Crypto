"""Candles backend — публичный BingX kline endpoint.

Используется для отрисовки графиков на TradeDetail (Lightweight Charts).
Auth не нужен — public market data. TTL cache 30 секунд чтобы не
давить BingX rate-limit при множественных кликах.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BINGX_BASE = "https://open-api.bingx.com"
_KLINES_PATH = "/openApi/swap/v3/quote/klines"
_TIMEOUT_S = 8.0
_TTL_S = 30.0
_VALID_INTERVALS = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"}


@dataclass(frozen=True)
class Candle:
    time_ms: int  # candle open time
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class _CacheEntry:
    candles: list[Candle]
    fetched_at_ts: float


class CandlesFetcher:
    """In-memory кеш BingX klines с TTL 30s.

    Использование:
        f = CandlesFetcher()
        candles = f.get("BTC-USDT", "15m", 100)
        # → list[Candle], последние 100 свечей
    """

    def __init__(
        self,
        *,
        base_url: str = _BINGX_BASE,
        ttl_s: float = _TTL_S,
    ) -> None:
        self._base_url = base_url
        self._ttl_s = ttl_s
        self._cache: dict[tuple[str, str, int], _CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, symbol: str, interval: str, limit: int = 100) -> list[Candle]:
        if interval not in _VALID_INTERVALS:
            raise ValueError(
                f"Invalid interval {interval!r}, expected one of {sorted(_VALID_INTERVALS)}"
            )
        if not (1 <= limit <= 1000):
            raise ValueError("limit must be in [1, 1000]")

        key = (symbol, interval, limit)
        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and time.time() - entry.fetched_at_ts < self._ttl_s:
                return entry.candles

            candles = self._fetch(symbol, interval, limit)
            self._cache[key] = _CacheEntry(candles=candles, fetched_at_ts=time.time())
            return candles

    def _fetch(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        try:
            with httpx.Client(timeout=_TIMEOUT_S) as client:
                resp = client.get(
                    f"{self._base_url}{_KLINES_PATH}",
                    params={"symbol": symbol, "interval": interval, "limit": str(limit)},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("BingX klines fetch failed: %s", e)
            return []

        if not isinstance(data, dict):
            return []
        items = data.get("data", [])
        if not isinstance(items, list):
            return []

        candles: list[Candle] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                candles.append(
                    Candle(
                        time_ms=int(item["time"]),
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=float(item.get("volume", 0) or 0),
                    )
                )
            except (KeyError, ValueError, TypeError):
                continue
        # BingX отдаёт DESC, переворачиваем в ASC для chart libs
        candles.sort(key=lambda c: c.time_ms)
        return candles


def candle_to_dict(c: Candle) -> dict[str, Any]:
    """Lightweight Charts ожидает {time: <unix sec>, open, high, low, close}."""
    return {
        "time": c.time_ms // 1000,
        "open": c.open,
        "high": c.high,
        "low": c.low,
        "close": c.close,
        "volume": c.volume,
    }
