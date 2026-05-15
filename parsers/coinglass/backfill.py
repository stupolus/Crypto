"""Coinglass → Static-провайдеры: bulk-backfill для бэктеста (план 21.4).

Один bulk-fetch истории ликвидаций+OI за период → наполняет
``StaticLiquidationProvider`` / ``StaticOpenInterestProvider`` (уже
оттестированы). Стратегия liquidation_reversal затем гоняется офлайн
по этим данным в BacktestEngine.

Symbol mapping: BingX-формат (``BTC-USDT``) → Coinglass
(exchange=``Binance``, symbol=``BTCUSDT``). Только мажоры на старте —
у них VST-ликвидность и Coinglass-история полные (план 21 §B2).

Без активного плана Coinglass клиент отдаёт пусто → провайдеры пустые
→ стратегия no-op (бэктест честно покажет 0 сделок, не упадёт).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal
from typing import TypeVar

from core.signals import (
    StaticDeltaProvider,
    StaticLiquidationProvider,
    StaticOpenInterestProvider,
)
from core.signals.liquidation_sweep import LiquidationBucket
from parsers.coinglass.client import CoinglassClient

logger = logging.getLogger(__name__)

# Длительность интервала в ms (Coinglass HOBBYIST: 4h+).
_INTERVAL_MS: dict[str, int] = {
    "4h": 4 * 3_600_000,
    "6h": 6 * 3_600_000,
    "8h": 8 * 3_600_000,
    "12h": 12 * 3_600_000,
    "1d": 24 * 3_600_000,
    "1w": 7 * 24 * 3_600_000,
}
_MAX_LIMIT = 1000

_T = TypeVar("_T")


def _paginate(
    fetch: Callable[[int, int], list[_T]],
    *,
    start_ms: int,
    end_ms: int,
    interval_ms: int,
    ts_of: Callable[[_T], int],
) -> list[_T]:
    """Окно-цикл: Coinglass отдаёт ≤1000 точек/запрос. Идём от start_ms
    вперёд окнами по 1000 баров, склеиваем, дедуп по ts.

    Останов: дошли до end_ms ИЛИ запрос вернул пусто (нет данных /
    план не активен) — защита от бесконечного цикла.
    """
    window_ms = _MAX_LIMIT * interval_ms
    seen: dict[int, _T] = {}
    cursor = start_ms
    guard = 0
    while cursor < end_ms and guard < 100:
        guard += 1
        win_end = min(cursor + window_ms, end_ms)
        rows = fetch(cursor, win_end)
        if not rows:
            break
        for r in rows:
            seen[ts_of(r)] = r
        max_ts = max(ts_of(r) for r in rows)
        if max_ts < cursor + interval_ms:
            break  # не продвинулись — стоп
        cursor = max_ts + interval_ms
    return [seen[k] for k in sorted(seen)]


# BingX symbol → (Coinglass exchange, Coinglass symbol, Coinglass OI coin).
_SYMBOL_MAP: dict[str, tuple[str, str, str]] = {
    "BTC-USDT": ("Binance", "BTCUSDT", "BTC"),
    "ETH-USDT": ("Binance", "ETHUSDT", "ETH"),
    "SOL-USDT": ("Binance", "SOLUSDT", "SOL"),
}


def map_symbol(bingx_symbol: str) -> tuple[str, str, str] | None:
    """BingX symbol → (exchange, cg_symbol, cg_coin) или None если нет."""
    return _SYMBOL_MAP.get(bingx_symbol)


def backfill_providers(
    bingx_symbol: str,
    interval: str,
    *,
    start_time_ms: int,
    end_time_ms: int,
    client: CoinglassClient | None = None,
) -> tuple[StaticLiquidationProvider, StaticOpenInterestProvider, StaticDeltaProvider]:
    """Скачать историю и собрать Static-провайдеры под backtest.

    Возвращает (liq, oi, delta). Пустые если symbol не в маппинге ИЛИ
    план Coinglass не активен (клиент → []). CVD из taker-volume
    (Coinglass) решает блокер B2 плана 21.
    """
    cg = client or CoinglassClient()
    mapping = map_symbol(bingx_symbol)
    if mapping is None:
        logger.warning("backfill: symbol %s не в _SYMBOL_MAP — пусто", bingx_symbol)
        return (
            StaticLiquidationProvider(),
            StaticOpenInterestProvider(),
            StaticDeltaProvider(),
        )

    exchange, cg_symbol, cg_coin = mapping
    interval_ms = _INTERVAL_MS.get(interval)

    if interval_ms is None:
        # Неизвестный/мелкий интервал — один запрос (≤1000 точек).
        liq_rows = cg.get_liquidation_history(
            exchange=exchange,
            symbol=cg_symbol,
            interval=interval,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )
        oi_rows = cg.get_open_interest_history(
            symbol=cg_coin,
            interval=interval,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )
        cvd_rows = cg.get_cvd_history(
            exchange=exchange,
            symbol=cg_symbol,
            interval=interval,
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms,
        )
    else:
        # Пагинация: окнами по 1000 баров покрываем весь диапазон.
        liq_rows = _paginate(
            lambda s, e: cg.get_liquidation_history(
                exchange=exchange,
                symbol=cg_symbol,
                interval=interval,
                start_time_ms=s,
                end_time_ms=e,
            ),
            start_ms=start_time_ms,
            end_ms=end_time_ms,
            interval_ms=interval_ms,
            ts_of=lambda r: r.timestamp_ms,
        )
        oi_rows = _paginate(
            lambda s, e: cg.get_open_interest_history(
                symbol=cg_coin,
                interval=interval,
                start_time_ms=s,
                end_time_ms=e,
            ),
            start_ms=start_time_ms,
            end_ms=end_time_ms,
            interval_ms=interval_ms,
            ts_of=lambda r: r[0],
        )
        cvd_rows = _paginate(
            lambda s, e: cg.get_cvd_history(
                exchange=exchange,
                symbol=cg_symbol,
                interval=interval,
                start_time_ms=s,
                end_time_ms=e,
            ),
            start_ms=start_time_ms,
            end_ms=end_time_ms,
            interval_ms=interval_ms,
            ts_of=lambda r: r[0],
        )

    buckets: dict[int, LiquidationBucket] = {
        r.timestamp_ms: LiquidationBucket(
            long_volume=r.long_liquidation_usd,
            short_volume=r.short_liquidation_usd,
        )
        for r in liq_rows
    }
    oi_series: list[tuple[int, Decimal]] = list(oi_rows)
    cvd_series: list[tuple[int, Decimal]] = list(cvd_rows)

    logger.info(
        "backfill %s: %d liq-buckets, %d oi-points, %d cvd-points (%s)",
        bingx_symbol,
        len(buckets),
        len(oi_series),
        len(cvd_series),
        "ПУСТО — план Coinglass не активен?" if not buckets and not oi_series else "ok",
    )
    return (
        StaticLiquidationProvider({bingx_symbol: buckets}),
        StaticOpenInterestProvider({bingx_symbol: oi_series}),
        StaticDeltaProvider({bingx_symbol: cvd_series}),
    )
