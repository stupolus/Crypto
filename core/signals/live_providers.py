"""Live-обёртки провайдеров для liquidation_reversal (план 21 фаза 21.3).

BingX отдаёт открытый интерес как snapshot (не временной ряд). Live-
стратегии нужен ряд — поэтому runner периодически поллит snapshot и
кладёт в in-memory ring через ``record``. Стратегия читает ``get_series``
(тот же протокол ``OpenInterestProvider``, что и Static-заглушка).

Coinglass-обёртка для ликвидаций — отдельная задача, ждёт API-ключ
(plan 21 TODO, бюджет одобрен 2026-05-15).
"""

from __future__ import annotations

import logging
import time
from collections import deque
from decimal import Decimal
from typing import Any

from core.signals.liquidation_sweep import LiquidationBucket

logger = logging.getLogger(__name__)

_DEFAULT_MAXLEN = 500


class RollingOpenInterestProvider:
    """In-memory ring OI per symbol. Runner кормит snapshot'ами.

    Реализует ``OpenInterestProvider`` (``get_series``). ``record``
    добавляет точку; дубликаты по ts игнорируются (idempotent poll).
    ``maxlen`` ограничивает память (по умолчанию 500 точек на symbol).
    """

    def __init__(self, maxlen: int = _DEFAULT_MAXLEN) -> None:
        self._maxlen = maxlen
        self._series: dict[str, deque[tuple[int, Decimal]]] = {}

    def record(self, symbol: str, timestamp_ms: int, oi: Decimal) -> None:
        dq = self._series.setdefault(symbol, deque(maxlen=self._maxlen))
        if dq and dq[-1][0] == timestamp_ms:
            return  # тот же срез — не дублируем
        dq.append((timestamp_ms, oi))

    def get_series(self, symbol: str, timestamp_ms: int, n: int) -> list[Decimal]:
        dq = self._series.get(symbol)
        if not dq:
            return []
        vals = [v for ts, v in dq if ts <= timestamp_ms]
        return vals[-n:]


async def poll_open_interest(
    public_api: object,
    symbol: str,
    provider: RollingOpenInterestProvider,
) -> bool:
    """Запросить текущий OI у BingX и записать в provider.

    ``public_api`` — ``adapters.bingx.public.PublicAPI`` (duck-typed
    чтобы не тащить адаптер в core). Best-effort: ошибка → False + log,
    runner не падает.
    """
    try:
        oi = await public_api.get_open_interest(symbol)  # type: ignore[attr-defined]
    except Exception as e:
        logger.warning("poll_open_interest failed for %s: %s", symbol, e)
        return False
    provider.record(symbol, oi.time_ms, oi.open_interest)
    return True


# ── Coinglass live-провайдеры (Ф1.2-live, план 01 §6h) ────────────────────
#
# Ленивая стратегия: на каждый get_* проверяем, не пора ли освежить кэш
# (last_refresh + min_refresh_seconds). Если пора — синхронный вызов
# Coinglass `*_history` (limit=1000), пересобираем кэш, дальше отдаём из
# кэша. Стратегия дёргает get_* на закрытии бара (4h/6h) → блокирующий
# вызов раз в несколько минут приемлем.

_DEFAULT_REFRESH_S = 150


class _ThrottledRefresh:
    """Хелпер: пускает refresh не чаще, чем раз в min_refresh_seconds."""

    def __init__(self, min_refresh_seconds: int) -> None:
        self._min = min_refresh_seconds
        self._last = 0.0

    def due(self, force: bool = False) -> bool:
        now = time.monotonic()
        if force or (now - self._last) >= self._min:
            self._last = now
            return True
        return False


class CoinglassLiveLiquidationProvider:
    """Live LiquidationProvider поверх Coinglass `get_liquidation_history`.

    Один экземпляр на символ. Кэш — dict[ts_ms → LiquidationBucket].
    """

    def __init__(
        self,
        client: Any,
        *,
        bingx_symbol: str,
        cg_symbol: str,
        exchange: str,
        interval: str,
        min_refresh_seconds: int = _DEFAULT_REFRESH_S,
    ) -> None:
        self._client = client
        self._sym = bingx_symbol
        self._cg = cg_symbol
        self._ex = exchange
        self._iv = interval
        self._cache: dict[int, LiquidationBucket] = {}
        self._refresh = _ThrottledRefresh(min_refresh_seconds)

    def _ensure_fresh(self) -> None:
        if not self._refresh.due(force=not self._cache):
            return
        try:
            rows = self._client.get_liquidation_history(
                exchange=self._ex, symbol=self._cg, interval=self._iv, limit=1000
            )
        except Exception as e:
            logger.warning("coinglass liq refresh failed: %s", e)
            return
        self._cache = {
            r.timestamp_ms: LiquidationBucket(
                long_volume=r.long_liquidation_usd,
                short_volume=r.short_liquidation_usd,
            )
            for r in rows
        }

    def get_bucket(self, symbol: str, timestamp_ms: int) -> LiquidationBucket | None:
        if symbol != self._sym:
            return None
        self._ensure_fresh()
        return self._cache.get(timestamp_ms)

    def get_baseline(self, symbol: str, timestamp_ms: int, n: int) -> list[LiquidationBucket]:
        if symbol != self._sym:
            return []
        self._ensure_fresh()
        prior = [b for ts, b in sorted(self._cache.items()) if ts < timestamp_ms]
        return prior[-n:]


class _SeriesCache:
    """Общий кэш-ряд (ts, value) ASC для OI/CVD live-провайдеров."""

    def __init__(
        self,
        client: Any,
        method_name: str,
        *,
        bingx_symbol: str,
        cg_symbol: str,
        exchange: str | None,
        interval: str,
        min_refresh_seconds: int,
    ) -> None:
        self._client = client
        self._method = method_name
        self._sym = bingx_symbol
        self._cg = cg_symbol
        self._ex = exchange
        self._iv = interval
        self._data: list[tuple[int, Decimal]] = []
        self._refresh = _ThrottledRefresh(min_refresh_seconds)

    def ensure_fresh(self) -> None:
        if not self._refresh.due(force=not self._data):
            return
        kwargs: dict[str, Any] = dict(symbol=self._cg, interval=self._iv, limit=1000)
        if self._ex is not None:
            kwargs["exchange"] = self._ex
        try:
            rows = getattr(self._client, self._method)(**kwargs)
        except Exception as e:
            logger.warning("coinglass %s refresh failed: %s", self._method, e)
            return
        self._data = sorted(rows)

    def values_at_or_before(self, ts: int, n: int) -> list[Decimal]:
        return [v for t, v in self._data if t <= ts][-n:]

    def symbol_matches(self, symbol: str) -> bool:
        return symbol == self._sym


class CoinglassLiveOpenInterestProvider:
    """Live OpenInterestProvider поверх Coinglass `get_open_interest_history`."""

    def __init__(
        self,
        client: Any,
        *,
        bingx_symbol: str,
        cg_symbol: str,
        exchange: str,
        interval: str,
        min_refresh_seconds: int = _DEFAULT_REFRESH_S,
    ) -> None:
        self._c = _SeriesCache(
            client,
            "get_open_interest_history",
            bingx_symbol=bingx_symbol,
            cg_symbol=cg_symbol,
            exchange=exchange,
            interval=interval,
            min_refresh_seconds=min_refresh_seconds,
        )

    def get_series(self, symbol: str, timestamp_ms: int, n: int) -> list[Decimal]:
        if not self._c.symbol_matches(symbol):
            return []
        self._c.ensure_fresh()
        return self._c.values_at_or_before(timestamp_ms, n)


class CoinglassLiveDeltaProvider:
    """Live DeltaProvider (CVD) поверх Coinglass `get_cvd_history`."""

    def __init__(
        self,
        client: Any,
        *,
        bingx_symbol: str,
        cg_symbol: str,
        exchange: str,
        interval: str,
        min_refresh_seconds: int = _DEFAULT_REFRESH_S,
    ) -> None:
        self._c = _SeriesCache(
            client,
            "get_cvd_history",
            bingx_symbol=bingx_symbol,
            cg_symbol=cg_symbol,
            exchange=exchange,
            interval=interval,
            min_refresh_seconds=min_refresh_seconds,
        )

    def get_cvd_series(self, symbol: str, timestamp_ms: int, n: int) -> list[Decimal]:
        if not self._c.symbol_matches(symbol):
            return []
        self._c.ensure_fresh()
        return self._c.values_at_or_before(timestamp_ms, n)


class CoinglassLiveFundingProvider:
    """Live FundingProvider поверх Coinglass `get_funding_history`.

    Возвращает последнее funding-значение ≤ ``timestamp_ms``.
    """

    def __init__(
        self,
        client: Any,
        *,
        bingx_symbol: str,
        cg_symbol: str,
        exchange: str,
        interval: str = "8h",
        min_refresh_seconds: int = _DEFAULT_REFRESH_S,
    ) -> None:
        self._c = _SeriesCache(
            client,
            "get_funding_history",
            bingx_symbol=bingx_symbol,
            cg_symbol=cg_symbol,
            exchange=exchange,
            interval=interval,
            min_refresh_seconds=min_refresh_seconds,
        )

    def get_funding_rate(self, symbol: str, timestamp_ms: int) -> Decimal | None:
        if not self._c.symbol_matches(symbol):
            return None
        self._c.ensure_fresh()
        vals = self._c.values_at_or_before(timestamp_ms, 1)
        return vals[-1] if vals else None


def build_coinglass_live_providers(
    client: Any,
    bingx_symbol: str,
    interval: str,
    *,
    funding_interval: str = "8h",
    min_refresh_seconds: int = _DEFAULT_REFRESH_S,
) -> (
    tuple[
        CoinglassLiveLiquidationProvider,
        CoinglassLiveOpenInterestProvider,
        CoinglassLiveDeltaProvider,
        CoinglassLiveFundingProvider,
    ]
    | None
):
    """Фабрика live-провайдеров для liquidation_reversal.

    Возвращает 4 провайдера (liq, oi, delta, funding) или ``None`` если
    символ не маппится на Coinglass (см. ``parsers.coinglass.backfill.
    map_symbol``). Все провайдеры используют один общий ``client``.
    """
    from parsers.coinglass.backfill import map_symbol

    mapping = map_symbol(bingx_symbol)
    if mapping is None:
        return None
    exchange, cg_symbol, _ = mapping
    liq = CoinglassLiveLiquidationProvider(
        client,
        bingx_symbol=bingx_symbol,
        cg_symbol=cg_symbol,
        exchange=exchange,
        interval=interval,
        min_refresh_seconds=min_refresh_seconds,
    )
    oi = CoinglassLiveOpenInterestProvider(
        client,
        bingx_symbol=bingx_symbol,
        cg_symbol=cg_symbol,
        exchange=exchange,
        interval=interval,
        min_refresh_seconds=min_refresh_seconds,
    )
    delta = CoinglassLiveDeltaProvider(
        client,
        bingx_symbol=bingx_symbol,
        cg_symbol=cg_symbol,
        exchange=exchange,
        interval=interval,
        min_refresh_seconds=min_refresh_seconds,
    )
    funding = CoinglassLiveFundingProvider(
        client,
        bingx_symbol=bingx_symbol,
        cg_symbol=cg_symbol,
        exchange=exchange,
        interval=funding_interval,
        min_refresh_seconds=min_refresh_seconds,
    )
    return liq, oi, delta, funding
