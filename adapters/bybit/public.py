"""Public API Bybit V5.

Эндпоинты без авторизации: ticker, klines.

Bybit V5 для USDT-перпов всегда требует ``category=linear``. Мы фиксируем
это значение в адаптере, чтобы стратегии не дублировали (план 49).
"""

from __future__ import annotations

from typing import Any

from adapters.bybit.client import BybitClient
from adapters.bybit.models import Kline, Ticker
from adapters.bybit.symbol import from_project_format


class PublicAPI:
    """Высокоуровневые public-эндпоинты Bybit V5."""

    CATEGORY = "linear"  # USDT-перпы — единственная категория в плане 49.

    def __init__(self, client: BybitClient) -> None:
        self._client = client

    async def get_kline(
        self,
        symbol: str,
        *,
        interval: str = "1",
        limit: int = 200,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> list[Kline]:
        """Получить klines. ``symbol`` в проектном формате (``BTC-USDT``).

        ``interval`` — строка Bybit V5: ``1, 3, 5, 15, 30, 60, 120, 240, 360,
        720, D, W, M``. Возвращаем в **ASC** порядке (Bybit отдаёт DESC).
        """
        params: dict[str, Any] = {
            "category": self.CATEGORY,
            "symbol": from_project_format(symbol),
            "interval": interval,
            "limit": limit,
        }
        if start_ms is not None:
            params["start"] = start_ms
        if end_ms is not None:
            params["end"] = end_ms

        data = await self._client.public_get("/v5/market/kline", params=params)
        rows = data.get("list") or []
        klines = [Kline.from_v5_row(row) for row in rows]
        klines.sort(key=lambda k: k.start_ms)  # ASC
        return klines

    async def get_ticker(self, symbol: str) -> Ticker:
        """Тикер для одного символа (проектный формат)."""
        params = {
            "category": self.CATEGORY,
            "symbol": from_project_format(symbol),
        }
        data = await self._client.public_get("/v5/market/tickers", params=params)
        lst = data.get("list") or []
        if not lst:
            raise ValueError(f"ticker list empty for {symbol}")
        # Bybit отдаёт symbol без дефиса — Ticker сам не конвертирует, но
        # для удобства подменяем обратно в проектный формат.
        raw = dict(lst[0])
        # symbol в проектный формат для консистентности:
        from adapters.bybit.symbol import to_project_format

        raw["symbol"] = to_project_format(raw["symbol"])
        return Ticker(**raw)
