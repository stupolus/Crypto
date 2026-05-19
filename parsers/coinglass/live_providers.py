"""Live Coinglass-провайдеры для composite_signal forward-демо (план 34).

Реализуют те же протоколы core.signals, что Static/backfill-версии, но
тянут свежее окно из Coinglass с time-кэшем (защита от 429: рефетч не
чаще ``refresh_s``). Слой parsers → зависит от core-протоколов, не
наоборот.

⚠️ Только для forward-демо ПОСЛЕ прохождения backfill-критерия
(план 33). Тариф Coinglass: интервал ≥ 4h.
"""

from __future__ import annotations

import logging
import time
from bisect import bisect_right
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from core.signals.liquidation_sweep import LiquidationBucket
from parsers.coinglass.backfill import map_symbol
from parsers.coinglass.client import CoinglassClient

logger = logging.getLogger(__name__)

_DEFAULT_REFRESH_S = 300  # 4h-бары меняются медленно — 5 мин кэша хватит
_WINDOW_BARS = 1000  # один запрос ≤1000 точек (без пагинации → без 429-шторма)


class _Cached:
    """Time-кэш одного ряда: рефетч не чаще refresh_s."""

    def __init__(self, refresh_s: int) -> None:
        self._refresh_s = refresh_s
        self._at = 0.0
        self._rows: list[Any] = []

    def get(self, fetch: Callable[[], list[Any]]) -> list[Any]:
        now = time.time()
        if not self._rows or now - self._at >= self._refresh_s:
            try:
                self._rows = fetch()
                self._at = now
            except Exception as e:
                logger.warning("coinglass live fetch failed: %s", e)
        return self._rows


class CoinglassLiveFundingProvider:
    def __init__(
        self,
        client: CoinglassClient,
        exchange: str,
        cg_symbol: str,
        interval: str,
        *,
        refresh_s: int = _DEFAULT_REFRESH_S,
    ) -> None:
        self._c = client
        self._ex = exchange
        self._sym = cg_symbol
        self._iv = interval
        self._cache = _Cached(refresh_s)

    def get_funding_rate(self, symbol: str, timestamp_ms: int) -> Decimal | None:
        rows = self._cache.get(
            lambda: self._c.get_funding_history(
                exchange=self._ex, symbol=self._sym, interval=self._iv, limit=_WINDOW_BARS
            )
        )
        if not rows:
            return None
        ts = [r[0] for r in rows]
        i = bisect_right(ts, timestamp_ms)
        return rows[i - 1][1] if i > 0 else None


class CoinglassLiveLiquidationProvider:
    def __init__(
        self,
        client: CoinglassClient,
        exchange: str,
        cg_symbol: str,
        interval: str,
        *,
        refresh_s: int = _DEFAULT_REFRESH_S,
    ) -> None:
        self._c = client
        self._ex = exchange
        self._sym = cg_symbol
        self._iv = interval
        self._cache = _Cached(refresh_s)

    def _buckets(self) -> list[tuple[int, LiquidationBucket]]:
        rows = self._cache.get(
            lambda: self._c.get_liquidation_history(
                exchange=self._ex, symbol=self._sym, interval=self._iv, limit=_WINDOW_BARS
            )
        )
        return [
            (
                r.timestamp_ms,
                LiquidationBucket(
                    long_volume=r.long_liquidation_usd, short_volume=r.short_liquidation_usd
                ),
            )
            for r in rows
        ]

    def get_bucket(self, symbol: str, timestamp_ms: int) -> LiquidationBucket | None:
        bs = self._buckets()
        prev = [(ts, b) for ts, b in bs if ts <= timestamp_ms]
        return prev[-1][1] if prev else None

    def get_baseline(self, symbol: str, timestamp_ms: int, n: int) -> list[LiquidationBucket]:
        bs = [(ts, b) for ts, b in self._buckets() if ts <= timestamp_ms]
        return [b for _ts, b in bs[-(n + 1) : -1]] if len(bs) > 1 else []


class CoinglassLiveOpenInterestProvider:
    def __init__(
        self,
        client: CoinglassClient,
        cg_coin: str,
        interval: str,
        *,
        refresh_s: int = _DEFAULT_REFRESH_S,
    ) -> None:
        self._c = client
        self._coin = cg_coin
        self._iv = interval
        self._cache = _Cached(refresh_s)

    def get_series(self, symbol: str, timestamp_ms: int, n: int) -> list[Decimal]:
        rows = self._cache.get(
            lambda: self._c.get_open_interest_history(
                symbol=self._coin, interval=self._iv, limit=_WINDOW_BARS
            )
        )
        return [v for ts, v in rows if ts <= timestamp_ms][-n:]


class CoinglassLiveDeltaProvider:
    def __init__(
        self,
        client: CoinglassClient,
        exchange: str,
        cg_symbol: str,
        interval: str,
        *,
        refresh_s: int = _DEFAULT_REFRESH_S,
    ) -> None:
        self._c = client
        self._ex = exchange
        self._sym = cg_symbol
        self._iv = interval
        self._cache = _Cached(refresh_s)

    def get_cvd_series(self, symbol: str, timestamp_ms: int, n: int) -> list[Decimal]:
        rows = self._cache.get(
            lambda: self._c.get_cvd_history(
                exchange=self._ex, symbol=self._sym, interval=self._iv, limit=_WINDOW_BARS
            )
        )
        return [v for ts, v in rows if ts <= timestamp_ms][-n:]


def build_live_providers(
    bingx_symbol: str,
    interval: str,
    *,
    client: CoinglassClient | None = None,
    refresh_s: int = _DEFAULT_REFRESH_S,
) -> (
    tuple[
        CoinglassLiveFundingProvider,
        CoinglassLiveLiquidationProvider,
        CoinglassLiveOpenInterestProvider,
        CoinglassLiveDeltaProvider,
    ]
    | None
):
    """(funding, liq, oi, delta) для composite или None если symbol не
    в Coinglass-маппинге."""
    mapping = map_symbol(bingx_symbol)
    if mapping is None:
        logger.warning("coinglass live: %s не в _SYMBOL_MAP", bingx_symbol)
        return None
    exchange, cg_symbol, cg_coin = mapping
    cg = client or CoinglassClient()
    return (
        CoinglassLiveFundingProvider(cg, exchange, cg_symbol, interval, refresh_s=refresh_s),
        CoinglassLiveLiquidationProvider(cg, exchange, cg_symbol, interval, refresh_s=refresh_s),
        CoinglassLiveOpenInterestProvider(cg, cg_coin, interval, refresh_s=refresh_s),
        CoinglassLiveDeltaProvider(cg, exchange, cg_symbol, interval, refresh_s=refresh_s),
    )
