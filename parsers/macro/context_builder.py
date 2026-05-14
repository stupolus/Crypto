"""MacroContextBuilder — связывает YfinanceAdapter + FREDAdapter в один MacroContextData.

Используется в hot loop: builder вызывается перед AgentTeam.evaluate_signal,
возвращает готовый MacroContextData для evaluate_with_team.

Embedded cache (TTL по умолчанию 1 час) — macro snapshot обновляется
редко, нет смысла дёргать yfinance/FRED на каждый Layer 2 сигнал.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal

from core.agents.evaluate import MacroContextData
from parsers.macro.fred_adapter import FREDAdapter, FREDSnapshot
from parsers.macro.models import MacroSnapshot
from parsers.macro.yfinance_adapter import YfinanceAdapter

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_TTL_S = 3600.0


@dataclass
class _CacheEntry:
    snapshot: MacroContextData
    fetched_at_ts: float


def _to_str(value: Decimal | None) -> str:
    """Decimal → string with '0' default для отсутствующих значений."""
    return str(value) if value is not None else "0"


class MacroContextBuilder:
    """Объединяет yfinance + FRED snapshots в один MacroContextData.

    DI обоих адаптеров через конструктор. Кеш на ``cache_ttl_s``
    секунд (по умолчанию 1 час).

    Использование::

        builder = MacroContextBuilder(yf_adapter, fred_adapter)
        ctx = await builder.build()  # → MacroContextData
        decision = await evaluate_with_team(..., macro_data=ctx)
    """

    def __init__(
        self,
        yfinance_adapter: YfinanceAdapter,
        fred_adapter: FREDAdapter,
        *,
        cache_ttl_s: float = _DEFAULT_CACHE_TTL_S,
    ) -> None:
        self._yf = yfinance_adapter
        self._fred = fred_adapter
        self._cache: _CacheEntry | None = None
        self._cache_ttl_s = cache_ttl_s

    async def build(self, *, btc_dominance_pct: str = "0") -> MacroContextData:
        """Собрать MacroContextData. Кешируется на cache_ttl_s.

        ``btc_dominance_pct`` — внешний параметр (из CoinGecko / etc),
        не из yfinance/FRED.
        """
        now = time.monotonic()
        if self._cache is not None and now - self._cache.fetched_at_ts < self._cache_ttl_s:
            return self._cache.snapshot

        # YfinanceAdapter.snapshot() синхронный (uses YahooFetcher protocol)
        yf_snap: MacroSnapshot = self._yf.snapshot()
        fred_snap: FREDSnapshot = self._fred.snapshot()

        # FRED 10Y yield — если есть, перекрываем yfinance ^TNX (FRED свежее)
        yield_10y_str = _to_str(yf_snap.yield_10y) if yf_snap.yield_10y is not None else "0"

        ctx = MacroContextData(
            dxy=_to_str(yf_snap.dxy),
            dxy_change_24h_pct=_to_str(yf_snap.dxy_change_24h_pct),
            vix=_to_str(yf_snap.vix),
            vix_change_24h_pct=_to_str(yf_snap.vix_change_24h_pct),
            spx=_to_str(yf_snap.spx),
            ndx=_to_str(yf_snap.ndx),
            gold=_to_str(yf_snap.gold),
            oil=_to_str(yf_snap.oil),
            yield_10y=yield_10y_str,
            btc_dominance_pct=btc_dominance_pct,
            fed_calendar="[]",  # отдельный источник, можно подключить
            earnings_schedule="[]",
        )
        # Логируем FRED данные (даже если не передаём прямо в Macro Analyst,
        # они доступны для extended use)
        if fred_snap.fed_funds_rate is not None:
            logger.info(
                "macro: Fed funds=%s, unemp=%s, yield spread=%s",
                fred_snap.fed_funds_rate,
                fred_snap.unemployment_rate,
                fred_snap.yield_spread_10y_2y,
            )

        self._cache = _CacheEntry(snapshot=ctx, fetched_at_ts=now)
        return ctx

    def invalidate_cache(self) -> None:
        """Принудительный сброс кеша. Для тестов / breaking events."""
        self._cache = None
