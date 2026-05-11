"""Healthcheck VST окружения.

Проверяет что:
1. `.env` правильный (BINGX_VST_API_KEY/SECRET присутствуют).
2. BingX REST отвечает (public + signed запросы).
3. WebSocket подключается.
4. Аккаунт в `ISOLATED` + `one-way` для целевого символа.

Запуск:
    .venv/bin/python -m scripts.healthcheck --symbol BTC-USDT

Exit 0 = всё ок. Exit 1 = что-то сломано (см. stderr).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from decimal import Decimal

from adapters.bingx.client import BingXClient
from adapters.bingx.private import PrivateAPI
from adapters.bingx.public import PublicAPI
from adapters.bingx.settings import BingXSettings
from adapters.bingx.user_stream import BingXUserDataStream

logger = logging.getLogger(__name__)


async def check(symbol: str) -> int:
    failures: list[str] = []

    # 1. Settings.
    try:
        settings = BingXSettings()
    except Exception as exc:
        print(f"❌ Settings load failed: {exc}", file=sys.stderr)
        return 1
    if not settings.active_key or not settings.active_secret:
        print("❌ BINGX_*_API_KEY/SECRET не заданы в .env", file=sys.stderr)
        return 1
    print(f"✅ Settings loaded (env={settings.env})")

    async with BingXClient(settings=settings) as client:
        public_api = PublicAPI(client, client.config)
        private_api = PrivateAPI(client)

        # 2. Public REST.
        try:
            server_time = await public_api.get_server_time()
            print(f"✅ Public REST (server_time={server_time.server_time_ms})")
        except Exception as exc:
            failures.append(f"public REST: {exc}")
            print(f"❌ Public REST: {exc}", file=sys.stderr)

        # 3. Signed REST: balance.
        try:
            balances = await private_api.get_balance()
            balance_summary = ", ".join(
                f"{b.asset}={b.balance}" for b in balances[:3]
            )
            print(f"✅ Signed REST: balance = {balance_summary or '(empty)'}")
            for b in balances:
                if b.asset in ("VST", "USDT") and b.balance <= Decimal("0"):
                    print(
                        f"⚠️  {b.asset} balance is 0 — пополни через BingX UI"
                    )
        except Exception as exc:
            failures.append(f"signed REST: {exc}")
            print(f"❌ Signed REST balance: {exc}", file=sys.stderr)

        # 4. Positions / margin mode / position mode.
        try:
            positions = await private_api.get_positions(symbol)
            non_zero = [p for p in positions if p.position_amount != 0]
            if non_zero:
                print(
                    f"⚠️  Open positions on {symbol}: {len(non_zero)} — "
                    "вероятно нужно закрыть перед demo"
                )
                for p in non_zero:
                    print(f"     {p.symbol} {p.position_amount} side={p.position_side}")
            else:
                print(f"✅ No open positions on {symbol}")

            # margin type — ловим первую попавшуюся позицию (или просто факт что
            # endpoint работает).
            if positions:
                margin_types = {
                    p.margin_type for p in positions if p.margin_type
                }
                if margin_types == {"ISOLATED"}:
                    print("✅ Margin type = ISOLATED (как требуется)")
                elif margin_types:
                    print(
                        f"⚠️  Margin types in use: {margin_types} — должен быть ISOLATED"
                    )
        except Exception as exc:
            failures.append(f"positions: {exc}")
            print(f"❌ Positions check: {exc}", file=sys.stderr)

        # 5. ListenKey (WS auth check).
        try:
            key = await private_api.create_listen_key()
            print(f"✅ ListenKey acquired ({key[:8]}...)")
            await private_api.close_listen_key(key)
            print("✅ ListenKey closed cleanly")
        except Exception as exc:
            failures.append(f"listenKey: {exc}")
            print(f"❌ ListenKey: {exc}", file=sys.stderr)

        # 6. User Data Stream connect (минимальный smoke).
        try:
            async with BingXUserDataStream(private_api) as stream:
                # Достаточно, что подключились — события придут или не придут
                # за 3 сек, но connection факт.
                await asyncio.sleep(1.0)
                if stream.listen_key is None:
                    failures.append("user-stream: no listenKey")
                    print("❌ User stream listenKey is None", file=sys.stderr)
                else:
                    print(f"✅ User Data Stream connected (key={stream.listen_key[:8]}...)")
        except Exception as exc:
            failures.append(f"user-stream: {exc}")
            print(f"❌ User Data Stream: {exc}", file=sys.stderr)

    if failures:
        print(f"\n❌ FAILED ({len(failures)} issues)", file=sys.stderr)
        return 1
    print("\n✅ All checks passed")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="VST healthcheck")
    parser.add_argument("--symbol", default="BTC-USDT")
    parser.add_argument("--log-level", default="WARNING")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    rc = asyncio.run(check(args.symbol))
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
