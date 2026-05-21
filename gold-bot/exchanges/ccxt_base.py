"""Общая реализация адаптера поверх ccxt (async).

Здесь только market-data методы (фаза 1C). Account и trading — фазы 1D/1E.
ccxt-ответы конвертируются в наши pydantic-модели; все числа через Decimal.
Конкретные биржи (bingx.py, bybit.py) — тонкие подклассы, задающие клиента
и квирки.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from exchanges.base import PriceLevel
from exchanges.models import OHLCV, Ticker
from exchanges.normalize import to_canonical


def _dec(value: Any) -> Decimal:
    """Decimal из ccxt-значения (float/str). None — ошибка (поле обязано быть)."""
    if value is None:
        raise ValueError("ожидалось число, получено None")
    return Decimal(str(value))


def _dec0(value: Any) -> Decimal:
    """Decimal из необязательного значения: None → 0."""
    return Decimal("0") if value is None else Decimal(str(value))


class CcxtAdapter:
    """База для биржевых адаптеров на ccxt. Хранит async-клиента ccxt."""

    name: str = "ccxt"

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def client(self) -> Any:
        return self._client

    async def close(self) -> None:
        await self._client.close()

    # ── Market data ──
    async def fetch_markets(self) -> list[str]:
        markets: dict[str, Any] = await self._client.load_markets()
        return sorted(markets.keys())

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[OHLCV]:
        raw: list[list[Any]] = await self._client.fetch_ohlcv(
            to_canonical(symbol), timeframe, since, limit
        )
        return [
            OHLCV(
                timestamp=int(row[0]),
                open=_dec(row[1]),
                high=_dec(row[2]),
                low=_dec(row[3]),
                close=_dec(row[4]),
                volume=_dec(row[5]),
            )
            for row in raw
        ]

    async def fetch_ticker(self, symbol: str) -> Ticker:
        canonical = to_canonical(symbol)
        t: dict[str, Any] = await self._client.fetch_ticker(canonical)
        return Ticker(
            symbol=canonical,
            last=_dec(t["last"]),
            bid=_dec(t["bid"]),
            ask=_dec(t["ask"]),
            quote_volume_24h=_dec0(t.get("quoteVolume")),
            timestamp=int(t.get("timestamp") or 0),
        )

    async def fetch_order_book(
        self, symbol: str, depth: int = 20
    ) -> tuple[list[PriceLevel], list[PriceLevel]]:
        ob: dict[str, Any] = await self._client.fetch_order_book(to_canonical(symbol), depth)
        bids: list[PriceLevel] = [(_dec(p), _dec(s)) for p, s in ob["bids"]]
        asks: list[PriceLevel] = [(_dec(p), _dec(s)) for p, s in ob["asks"]]
        return bids, asks

    async def fetch_funding_rate(self, symbol: str) -> tuple[Decimal, int]:
        fr: dict[str, Any] = await self._client.fetch_funding_rate(to_canonical(symbol))
        rate = _dec0(fr.get("fundingRate"))
        next_ts = int(fr.get("fundingTimestamp") or fr.get("nextFundingTime") or 0)
        return rate, next_ts
