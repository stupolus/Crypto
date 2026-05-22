"""Smoke-проверка биржевого адаптера: публичные данные + (если ключи) баланс.

Запуск из каталога gold-bot:
    python -m scripts.smoke_exchange --exchange bingx --symbol BTC/USDT:USDT

BingX по умолчанию — VST (demo), читает BINGX_VST_API_KEY/SECRET. Live только
при BINGX_LIVE=1 (BINGX_API_KEY/SECRET). Bybit: BYBIT_API_KEY/SECRET, testnet — BYBIT_TESTNET=1.
Без ключей печатает только публичные данные (markets, ticker).
"""

from __future__ import annotations

import argparse
import asyncio
import os

from exchanges.bingx import BingXAdapter
from exchanges.bybit import BybitAdapter
from exchanges.ccxt_base import CcxtAdapter

_TRUE = {"1", "true", "yes"}


def _build(exchange: str) -> CcxtAdapter:
    if exchange == "bingx":
        # Дефолт — VST (demo). Live только явным BINGX_LIVE=1.
        if os.environ.get("BINGX_LIVE", "").lower() in _TRUE:
            return BingXAdapter(
                os.environ.get("BINGX_API_KEY", ""),
                os.environ.get("BINGX_API_SECRET", ""),
                vst=False,
            )
        return BingXAdapter(
            os.environ.get("BINGX_VST_API_KEY", ""),
            os.environ.get("BINGX_VST_API_SECRET", ""),
            vst=True,
        )
    testnet = os.environ.get("BYBIT_TESTNET", "").lower() in _TRUE
    return BybitAdapter(
        os.environ.get("BYBIT_API_KEY", ""),
        os.environ.get("BYBIT_API_SECRET", ""),
        testnet=testnet,
    )


async def _run(exchange: str, symbol: str) -> None:
    adapter = _build(exchange)
    try:
        markets = await adapter.fetch_markets()
        print(f"[{exchange}] markets: {len(markets)}")
        ticker = await adapter.fetch_ticker(symbol)
        print(f"[{exchange}] {ticker.symbol} last={ticker.last} spread={ticker.spread}")
        try:
            balance = await adapter.fetch_balance()
            print(f"[{exchange}] balance USDT total={balance.total}")
        except Exception as exc:
            print(f"[{exchange}] balance недоступен (нет ключей?): {type(exc).__name__}")
    finally:
        await adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-проверка биржевого адаптера gold-bot")
    parser.add_argument("--exchange", choices=["bingx", "bybit"], required=True)
    parser.add_argument("--symbol", default="BTC/USDT:USDT")
    args = parser.parse_args()
    asyncio.run(_run(args.exchange, args.symbol))


if __name__ == "__main__":
    main()
