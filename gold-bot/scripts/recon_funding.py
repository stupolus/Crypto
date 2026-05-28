"""Recon фазы 11B: качаем funding-историю BingX+Bybit, считаем |Δ| статистику.

Цель: до написания funding-arb стратегии узнать, действительно ли funding-rates
расходятся между биржами на XAUT настолько, чтобы покрыть round-trip cost.

Запуск из gold-bot:
    python -m scripts.recon_funding --symbol "XAUT/USDT:USDT" --months 12

Печатает:
- сколько funding-точек на каждой бирже
- сколько paired (выровненных по timestamp с tolerance 1 мин)
- median/max/p90 |Δ| funding
- вердикт: гипотеза funding-arb жива или мертва на recon-стадии

Сохраняет funding-данные в data/funding/{exchange}/{symbol}.parquet
для последующего полного бэктеста.

Ключей не требует — funding history публичная.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from decimal import Decimal
from pathlib import Path

from exchanges.bingx import BingXAdapter
from exchanges.bybit import BybitAdapter
from exchanges.ccxt_base import CcxtAdapter
from marketdata.funding import (
    align_funding_pair,
    divergence_stats,
    download_funding_history,
    funding_path,
    save_parquet,
)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MONTH_MS = 30 * 86_400_000

# Эмпирический порог: round-trip cost funding-arb ≈ 4×0.05% = 0.2% от notional.
# Для funding-выплаты 0.01% на $50k notional получаем $5 / 4 ноги cost ≈ $100
# → нерентабельно. Чтобы funding edge перекрыл cost минимум в 3 раза,
# медиана |Δ| должна быть ≥ ~0.05% за funding-период (≈ 0.005% за 8h).
_KILL_THRESHOLD_PCT = Decimal("0.00005")  # 0.005%


def _build(exchange: str) -> CcxtAdapter:
    if exchange == "bingx":
        return BingXAdapter("", "", vst=False)
    return BybitAdapter("", "", testnet=False)


async def _run(symbol: str, months: int) -> None:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - months * _MONTH_MS

    bingx = _build("bingx")
    bybit = _build("bybit")
    try:
        await bingx.fetch_markets()
        await bybit.fetch_markets()

        print(f"Качаем funding для {symbol} за {months} месяцев на обеих биржах...")
        bingx_rates = await download_funding_history(
            bingx, symbol, start_ms=start_ms, end_ms=end_ms
        )
        bybit_rates = await download_funding_history(
            bybit, symbol, start_ms=start_ms, end_ms=end_ms
        )

        print(f"  BingX: {len(bingx_rates)} точек")
        print(f"  Bybit: {len(bybit_rates)} точек")

        if bingx_rates:
            save_parquet(bingx_rates, funding_path(_DATA_DIR, "bingx", symbol))
        if bybit_rates:
            save_parquet(bybit_rates, funding_path(_DATA_DIR, "bybit", symbol))

        if not bingx_rates or not bybit_rates:
            print("\n⚠️  На одной из бирж нет funding-данных. Гипотеза 11 невыполнима.")
            return

        paired = align_funding_pair(bingx_rates, bybit_rates, tolerance_ms=60_000)
        stats = divergence_stats(paired)

        print("\n=== Статистика расхождения funding (|Δ|) ===")
        print(f"  Пар выровнено: {stats['n']}")
        median = stats["median_abs_diff"]
        p90 = stats["p90_abs_diff"]
        max_d = stats["max_abs_diff"]
        assert isinstance(median, Decimal)
        assert isinstance(p90, Decimal)
        assert isinstance(max_d, Decimal)
        print(f"  Медиана |Δ|: {median} ({median * Decimal(100):.4f}%)")
        print(f"  p90 |Δ|:     {p90} ({p90 * Decimal(100):.4f}%)")
        print(f"  Максимум:    {max_d} ({max_d * Decimal(100):.4f}%)")
        print(f"  Порог kill:  {_KILL_THRESHOLD_PCT} ({_KILL_THRESHOLD_PCT * Decimal(100):.4f}%)")

        print("\n=== Вердикт ===")
        if median < _KILL_THRESHOLD_PCT:
            print(
                f"❌ FAIL на recon: median |Δ| {median} < {_KILL_THRESHOLD_PCT}. "
                "Funding-arb edge на XAUT отсутствует. Гипотеза 11 закрывается, "
                "стратегию НЕ пишем."
            )
        else:
            print(
                f"✅ PASS recon: median |Δ| {median} >= {_KILL_THRESHOLD_PCT}. "
                "Идём в фазу 11C (написание стратегии funding_arb)."
            )
    finally:
        await bingx.close()
        await bybit.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Recon фазы 11B: funding divergence")
    parser.add_argument("--symbol", default="XAUT/USDT:USDT")
    parser.add_argument("--months", type=int, default=12)
    args = parser.parse_args()
    asyncio.run(_run(args.symbol, args.months))


if __name__ == "__main__":
    main()
