"""Скачать исторические свечи и сохранить в parquet.

Запуск из каталога gold-bot:
    python -m scripts.download_klines --exchange bingx --symbol BTC/USDT:USDT --timeframe 15m --months 12

Свечи публичны → берутся с ПРОДАКШН-эндпоинта без ключей (VST/demo исторические
свечи не отдаёт; бэктесту нужна реальная история). Файл кладётся в
gold-bot/data/candles/{exchange}/{symbol}/{tf}.parquet.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from exchanges.bingx import BingXAdapter
from exchanges.bybit import BybitAdapter
from exchanges.ccxt_base import CcxtAdapter
from marketdata.candles import candles_path, download_ohlcv, save_parquet

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MONTH_MS = 30 * 86_400_000


def _build(exchange: str) -> CcxtAdapter:
    # Исторические свечи публичны: продакшн-эндпоинт, без ключей, без VST/testnet.
    if exchange == "bingx":
        return BingXAdapter("", "", vst=False)
    return BybitAdapter("", "", testnet=False)


async def _run(exchange: str, symbol: str, timeframe: str, months: int) -> None:
    adapter = _build(exchange)
    try:
        await adapter.fetch_markets()  # прогрев рынков, чтобы символ резолвился
        start_ms = int(time.time() * 1000) - months * _MONTH_MS
        candles = await download_ohlcv(adapter, symbol, timeframe, start_ms=start_ms)
        if not candles:
            print(
                f"[{exchange}] {symbol} {timeframe}: 0 свечей. "
                "Проверь символ (есть ли в fetch_markets) и глубину истории биржи "
                "(BingX отдаёт ограниченное прошлое — попробуй меньше --months)."
            )
            return
        path = candles_path(_DATA_DIR, exchange, symbol, timeframe)
        save_parquet(candles, path)
        print(f"[{exchange}] {symbol} {timeframe}: {len(candles)} свечей → {path}")
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Скачать свечи в parquet (gold-bot)")
    parser.add_argument("--exchange", choices=["bingx", "bybit"], required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--months", type=int, default=6)
    args = parser.parse_args()
    asyncio.run(_run(args.exchange, args.symbol, args.timeframe, args.months))


if __name__ == "__main__":
    main()
