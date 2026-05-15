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
from decimal import Decimal

from core.signals import (
    StaticDeltaProvider,
    StaticLiquidationProvider,
    StaticOpenInterestProvider,
)
from core.signals.liquidation_sweep import LiquidationBucket
from parsers.coinglass.client import CoinglassClient

logger = logging.getLogger(__name__)

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

    liq_rows = cg.get_liquidation_history(
        exchange=exchange,
        symbol=cg_symbol,
        interval=interval,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
    )
    buckets: dict[int, LiquidationBucket] = {
        r.timestamp_ms: LiquidationBucket(
            long_volume=r.long_liquidation_usd,
            short_volume=r.short_liquidation_usd,
        )
        for r in liq_rows
    }

    oi_rows = cg.get_open_interest_history(
        symbol=cg_coin,
        interval=interval,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
    )
    oi_series: list[tuple[int, Decimal]] = list(oi_rows)

    cvd_rows = cg.get_cvd_history(
        exchange=exchange,
        symbol=cg_symbol,
        interval=interval,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
    )
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
