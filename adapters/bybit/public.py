"""Bybit V5 public REST API — ТОЛЬКО market-data (read-only).

В этом модуле НЕТ trading-методов и НЕТ HMAC-подписи запросов. Если
понадобится trading — это отдельный модуль с отдельным review.

Bybit V5 docs: https://bybit-exchange.github.io/docs/v5/intro
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Literal

import httpx

from adapters.bybit.models import BybitFundingRate, BybitKline, BybitOISample
from adapters.bybit.settings import BybitSettings

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_S = 20.0
_MAX_KLINE_LIMIT = 1000
_MAX_OI_LIMIT = 200

# Kline interval: 1, 3, 5, 15, 30, 60, 120, 240, 360, 720 (мин), D, W, M.
_KLINE_INTERVAL: dict[str, str] = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "D",
    "1w": "W",
}

# Open interest intervalTime: 5min, 15min, 30min, 1h, 4h, 1d.
_OI_INTERVAL: dict[str, str] = {
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


class BybitAPIError(Exception):
    """Bybit вернул retCode != 0."""

    def __init__(self, code: int, message: str, path: str) -> None:
        super().__init__(f"Bybit V5 error {code} at {path}: {message}")
        self.code = code
        self.message = message
        self.path = path


class BybitPublicAPI:
    """Async-клиент Bybit V5 public endpoints.

    Использование:
        async with BybitPublicAPI() as api:
            klines = await api.get_klines("BTCUSDT", "15m", limit=1000)

    Аутентификация: опциональный заголовок ``X-BAPI-API-KEY`` (без
    подписи — public-only). Если ключ задан в .env, отправляется для
    повышения rate-limit. Если нет — работаем без auth.
    """

    def __init__(
        self,
        settings: BybitSettings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        category: Literal["linear", "inverse", "spot"] = "linear",
    ) -> None:
        self._settings = settings or BybitSettings()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=self._settings.base_url, timeout=_DEFAULT_TIMEOUT_S
        )
        self._category = category

    async def __aenter__(self) -> BybitPublicAPI:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        key = self._settings.api_key
        return {"X-BAPI-API-KEY": key} if key else {}

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        r = await self._client.get(path, params=params, headers=self._headers())
        data: dict[str, Any] = r.json()
        code = int(data.get("retCode", -1))
        if code != 0:
            raise BybitAPIError(code=code, message=str(data.get("retMsg", "")), path=path)
        return data

    async def server_time_ms(self) -> int:
        """Серверное время Bybit, ms."""
        data = await self._get("/v5/market/time", {})
        # result.timeNano (string ns) или timeSecond (string s).
        result = data.get("result") or {}
        nano = result.get("timeNano")
        if nano is not None:
            return int(nano) // 1_000_000
        return int(float(result.get("timeSecond", "0")) * 1000)

    async def get_klines(
        self,
        symbol: str,
        timeframe: str,
        *,
        limit: int = 1000,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[BybitKline]:
        """``/v5/market/kline``. Bybit возвращает rows от newest к oldest.

        Сортируем по возрастанию времени.
        """
        iv = _KLINE_INTERVAL.get(timeframe)
        if iv is None:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        params: dict[str, Any] = {
            "category": self._category,
            "symbol": symbol,
            "interval": iv,
            "limit": min(max(limit, 1), _MAX_KLINE_LIMIT),
        }
        if start_ms is not None:
            params["start"] = start_ms
        if end_ms is not None:
            params["end"] = end_ms
        data = await self._get("/v5/market/kline", params)
        rows = (data.get("result") or {}).get("list") or []
        out = [
            BybitKline(
                start_time_ms=int(r[0]),
                open=Decimal(r[1]),
                high=Decimal(r[2]),
                low=Decimal(r[3]),
                close=Decimal(r[4]),
                volume=Decimal(r[5]),
                turnover=Decimal(r[6]),
            )
            for r in rows
        ]
        out.sort(key=lambda k: k.start_time_ms)
        return out

    async def get_open_interest_history(
        self,
        symbol: str,
        timeframe: str,
        *,
        limit: int = 200,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[BybitOISample]:
        """``/v5/market/open-interest``. ASC по времени."""
        iv = _OI_INTERVAL.get(timeframe)
        if iv is None:
            raise ValueError(f"unsupported OI timeframe: {timeframe}")
        params: dict[str, Any] = {
            "category": self._category,
            "symbol": symbol,
            "intervalTime": iv,
            "limit": min(max(limit, 1), _MAX_OI_LIMIT),
        }
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        data = await self._get("/v5/market/open-interest", params)
        rows = (data.get("result") or {}).get("list") or []
        out = [
            BybitOISample(
                timestamp_ms=int(r["timestamp"]),
                open_interest=Decimal(r["openInterest"]),
            )
            for r in rows
        ]
        out.sort(key=lambda s: s.timestamp_ms)
        return out

    async def get_funding_history(
        self,
        symbol: str,
        *,
        limit: int = 200,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[BybitFundingRate]:
        """``/v5/market/funding/history``. ASC по времени."""
        params: dict[str, Any] = {
            "category": self._category,
            "symbol": symbol,
            "limit": min(max(limit, 1), 200),
        }
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        data = await self._get("/v5/market/funding/history", params)
        rows = (data.get("result") or {}).get("list") or []
        out = [
            BybitFundingRate(
                symbol=str(r["symbol"]),
                funding_rate=Decimal(r["fundingRate"]),
                funding_rate_timestamp_ms=int(r["fundingRateTimestamp"]),
            )
            for r in rows
        ]
        out.sort(key=lambda f: f.funding_rate_timestamp_ms)
        return out
