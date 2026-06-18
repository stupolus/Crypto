"""Абстрактный интерфейс адаптера биржи.

Вышестоящие модули (стратегии, paper-runner, live-runner) зависят от этого
протокола, а не от конкретной биржи. Реализации появятся в фазах 1C-1E:
bingx.py, bybit.py.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from exchanges.models import (
    OHLCV,
    Balance,
    MarginMode,
    OrderRequest,
    OrderResult,
    Position,
    Ticker,
)

# (price, size) уровень стакана.
PriceLevel = tuple[Decimal, Decimal]


@runtime_checkable
class ExchangeAdapter(Protocol):
    """Единый интерфейс к перп-бирже. Все методы async."""

    name: str

    # ── Market data ──
    async def fetch_markets(self) -> list[str]:
        """Список доступных символов (для проверки наличия инструмента)."""
        ...

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[OHLCV]: ...

    async def fetch_ticker(self, symbol: str) -> Ticker: ...

    async def fetch_order_book(
        self, symbol: str, depth: int = 20
    ) -> tuple[list[PriceLevel], list[PriceLevel]]:
        """Возвращает (bids, asks)."""
        ...

    async def fetch_funding_rate(self, symbol: str) -> tuple[Decimal, int]:
        """Возвращает (rate, next_funding_ms)."""
        ...

    # ── Account ──
    async def fetch_balance(self) -> Balance: ...

    async def fetch_positions(self, symbols: list[str] | None = None) -> list[Position]: ...

    async def set_leverage(self, symbol: str, leverage: int) -> None: ...

    async def set_margin_mode(
        self, symbol: str, mode: MarginMode = MarginMode.ISOLATED
    ) -> None: ...

    # ── Trading ──
    async def place_order(self, request: OrderRequest) -> OrderResult: ...

    async def cancel_order(self, order_id: str, symbol: str) -> None: ...

    async def cancel_all_orders(self, symbol: str) -> None: ...

    async def close_position(self, symbol: str) -> OrderResult: ...

    async def fetch_order(self, order_id: str, symbol: str) -> OrderResult: ...

    async def fetch_open_orders(self, symbol: str | None = None) -> list[OrderResult]: ...
