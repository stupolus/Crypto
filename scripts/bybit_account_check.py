"""Read-only smoke-проверка Bybit-аккаунта (план 49.3, preflight).

Аналог ``gtaa_vst_executor --check`` для BingX: НИ ОДНОГО ордера, только
public-эндпоинты + signed-чтения (balance/positions). Запускается ПЕРВЫМ
после того, как ключи положены в ``/etc/crypto/.env``.

Что делает:
1. Читает ``BybitSettings`` из env/``.env``, печатает env (testnet/live),
   наличие ключей.
2. Public:
   - ``/v5/market/time`` — связь + time-offset.
   - ``/v5/market/tickers?category=linear&symbol=BTC-USDT`` — публичные
     цены работают.
3. Signed (если есть ключи):
   - ``/v5/account/wallet-balance`` — баланс UNIFIED.
   - ``/v5/position/list?symbol=BTC-USDT`` — позиции.

Запуск:
    .venv/bin/python -m scripts.bybit_account_check
    .venv/bin/python -m scripts.bybit_account_check --symbol ETH-USDT

⚠️ Из dev-окружения Bybit может вернуть 403 (CloudFront geoblock).
Скрипт запускается с VPS, где Bybit доступен.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal

from adapters.bybit import (
    APIError,
    AuthError,
    BybitClient,
    BybitSettings,
    NetworkError,
    PrivateAPI,
    PublicAPI,
    load_settings,
)


async def _check(symbol: str) -> int:
    """Возвращает exit-код: 0 = ok, 1 = есть проблемы."""
    settings: BybitSettings = load_settings()
    errors: list[str] = []

    print("Bybit account smoke-check (read-only, без ордеров)")
    print(f"  env: {settings.env}  ({settings.rest_base_url})")
    print(f"  recv_window_ms: {settings.recv_window_ms}")
    print(f"  ключи: {'есть' if settings.has_credentials() else 'НЕТ'}")
    print(f"  активный ключ: {(settings.active_key or '<none>')[:8]}***")

    async with BybitClient(settings=settings) as c:
        # 1. Time sync.
        try:
            offset_ms = await c.sync_time()
            print(f"\n[1/3] /v5/market/time: offset={offset_ms} ms")
            if abs(offset_ms) > settings.recv_window_ms:
                errors.append(
                    f"time-offset {offset_ms}ms > recv_window {settings.recv_window_ms}ms"
                )
        except (APIError, AuthError, NetworkError) as e:
            errors.append(f"time: {type(e).__name__}: {e}")
            print(f"\n[1/3] /v5/market/time: ОШИБКА {type(e).__name__}")
            return _finalize(errors)

        # 2. Public ticker.
        try:
            t = await PublicAPI(c).get_ticker(symbol)
            print(f"[2/3] /v5/market/tickers {symbol}: last={t.last_price} mark={t.mark_price}")
        except (APIError, NetworkError, ValueError) as e:
            errors.append(f"ticker: {type(e).__name__}: {e}")
            print(f"[2/3] /v5/market/tickers {symbol}: ОШИБКА {type(e).__name__}")

        # 3. Signed (если есть ключи).
        if not settings.has_credentials():
            print(f"\n[3/3] signed-вызовы пропущены: нет ключей для env={settings.env}")
        else:
            try:
                balances = await PrivateAPI(c).get_balance()
                usdt = next(
                    (b for b in balances if b.coin == "USDT"),
                    None,
                )
                if usdt is None:
                    print("[3/3] balance: нет USDT (testnet — нужен faucet?)")
                else:
                    print(f"[3/3] balance USDT: equity={usdt.equity} wallet={usdt.wallet_balance}")
                    if usdt.equity == Decimal("0"):
                        errors.append("USDT equity = 0 (testnet → faucet/deposit)")
            except AuthError as e:
                errors.append(f"balance auth: {e}")
                print(f"[3/3] balance: AUTH ERROR — {e}")
            except (APIError, NetworkError) as e:
                errors.append(f"balance: {type(e).__name__}: {e}")
                print(f"[3/3] balance: ОШИБКА {type(e).__name__}")

            # Позиции (если баланс прошёл).
            try:
                positions = await PrivateAPI(c).get_positions(symbol)
                if not positions:
                    print(f"     positions {symbol}: flat (нет открытых)")
                else:
                    for p in positions:
                        print(
                            f"     position {p.symbol} idx={p.position_idx} "
                            f"side={p.side} size={p.size} avg={p.avg_price}"
                        )
            except (APIError, AuthError, NetworkError) as e:
                errors.append(f"positions: {type(e).__name__}: {e}")
                print(f"     positions: ОШИБКА {type(e).__name__}")

    return _finalize(errors)


def _finalize(errors: list[str]) -> int:
    print()
    if errors:
        print("ИТОГ: ЕСТЬ ПРОБЛЕМЫ")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("ИТОГ: ГОТОВ К ИСПОЛЬЗОВАНИЮ (read-only)")
    print("Следующий шаг — отдельный план для фазы 49.3 (testnet smoke с ордерами).")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only smoke-проверка Bybit-аккаунта")
    parser.add_argument(
        "--symbol",
        default="BTC-USDT",
        help="Проектный формат, e.g. BTC-USDT. По умолчанию BTC-USDT.",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_check(args.symbol)))


if __name__ == "__main__":
    main()
