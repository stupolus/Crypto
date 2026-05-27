"""Тесты smoke-функции bybit_account_check (без сети, respx-моки).

Сам main() с argparse не тестируется — это shell-entry.
Тестируем `_check()` как корутину с моками HTTP.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
import respx

from scripts.bybit_account_check import _check


def _ok(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "retCode": 0,
        "retMsg": "OK",
        "result": result,
        "retExtInfo": {},
        "time": 1700000000000,
    }


@pytest.mark.asyncio
async def test_check_succeeds_with_full_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Полный успешный сценарий: time + ticker + balance + positions."""
    # Подсовываем чистый testnet-конфиг с тестовыми ключами.
    monkeypatch.setenv("BYBIT_ENV", "testnet")
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "k")
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "s")

    async with respx.mock(base_url="https://api-testnet.bybit.com") as mock:
        mock.get("/v5/market/time").mock(
            return_value=httpx.Response(200, json=_ok({"timeSecond": str(int(time.time()))}))
        )
        mock.get("/v5/market/tickers").mock(
            return_value=httpx.Response(
                200,
                json=_ok(
                    {
                        "list": [
                            {
                                "symbol": "BTCUSDT",
                                "lastPrice": "30000",
                                "markPrice": "30000",
                                "indexPrice": "30000",
                            }
                        ]
                    }
                ),
            )
        )
        mock.get("/v5/account/wallet-balance").mock(
            return_value=httpx.Response(
                200,
                json=_ok(
                    {
                        "list": [
                            {
                                "coin": [
                                    {
                                        "coin": "USDT",
                                        "equity": "10000",
                                        "walletBalance": "10000",
                                    }
                                ]
                            }
                        ]
                    }
                ),
            )
        )
        mock.get("/v5/position/list").mock(return_value=httpx.Response(200, json=_ok({"list": []})))
        exit_code = await _check("BTC-USDT")
    assert exit_code == 0


@pytest.mark.asyncio
async def test_check_warns_on_zero_usdt_equity(monkeypatch: pytest.MonkeyPatch) -> None:
    """USDT equity = 0 (testnet без faucet) → exit_code=1, в errors."""
    monkeypatch.setenv("BYBIT_ENV", "testnet")
    monkeypatch.setenv("BYBIT_TESTNET_API_KEY", "k")
    monkeypatch.setenv("BYBIT_TESTNET_API_SECRET", "s")
    async with respx.mock(base_url="https://api-testnet.bybit.com") as mock:
        mock.get("/v5/market/time").mock(
            return_value=httpx.Response(200, json=_ok({"timeSecond": str(int(time.time()))}))
        )
        mock.get("/v5/market/tickers").mock(
            return_value=httpx.Response(
                200,
                json=_ok(
                    {
                        "list": [
                            {
                                "symbol": "BTCUSDT",
                                "lastPrice": "1",
                                "markPrice": "1",
                                "indexPrice": "1",
                            }
                        ]
                    }
                ),
            )
        )
        mock.get("/v5/account/wallet-balance").mock(
            return_value=httpx.Response(
                200,
                json=_ok(
                    {
                        "list": [
                            {
                                "coin": [
                                    {
                                        "coin": "USDT",
                                        "equity": "0",
                                        "walletBalance": "0",
                                    }
                                ]
                            }
                        ]
                    }
                ),
            )
        )
        mock.get("/v5/position/list").mock(return_value=httpx.Response(200, json=_ok({"list": []})))
        exit_code = await _check("BTC-USDT")
    assert exit_code == 1


@pytest.mark.asyncio
async def test_check_no_keys_skips_signed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без ключей — signed-вызовы скипаем, но time + ticker всё равно ок."""
    # Явно сбрасываем ключи.
    for var in (
        "BYBIT_ENV",
        "BYBIT_TESTNET_API_KEY",
        "BYBIT_TESTNET_API_SECRET",
        "BYBIT_LIVE_API_KEY",
        "BYBIT_LIVE_API_SECRET",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BYBIT_ENV", "testnet")

    async with respx.mock(base_url="https://api-testnet.bybit.com") as mock:
        mock.get("/v5/market/time").mock(
            return_value=httpx.Response(200, json=_ok({"timeSecond": str(int(time.time()))}))
        )
        mock.get("/v5/market/tickers").mock(
            return_value=httpx.Response(
                200,
                json=_ok(
                    {
                        "list": [
                            {
                                "symbol": "BTCUSDT",
                                "lastPrice": "1",
                                "markPrice": "1",
                                "indexPrice": "1",
                            }
                        ]
                    }
                ),
            )
        )
        exit_code = await _check("BTC-USDT")
    # Нет ключей — signed скипнут, но публичные прошли → ok.
    assert exit_code == 0
