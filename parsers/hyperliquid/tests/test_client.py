"""Тесты Hyperliquid public-клиента (план 22 фаза 22.C)."""

from __future__ import annotations

from decimal import Decimal

import httpx
import respx

from parsers.hyperliquid import HyperliquidClient

_BASE = "https://api.hyperliquid.xyz"


def _cli() -> HyperliquidClient:
    return HyperliquidClient(client=httpx.Client(base_url=_BASE))


@respx.mock
def test_get_asset_contexts_parses_parallel_arrays() -> None:
    respx.post(f"{_BASE}/info").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"universe": [{"name": "BTC"}, {"name": "HYPE"}]},
                [
                    {
                        "markPx": "100000",
                        "oraclePx": "99990",
                        "openInterest": "12.5",
                        "funding": "0.0000125",
                        "dayNtlVlm": "5000000",
                    },
                    {
                        "markPx": "44.5",
                        "oraclePx": "44.4",
                        "openInterest": "1000",
                        "funding": "-0.00002",
                        "dayNtlVlm": "93000000",
                    },
                ],
            ],
        )
    )
    ctxs = _cli().get_asset_contexts()
    assert [c.coin for c in ctxs] == ["BTC", "HYPE"]
    btc = ctxs[0]
    assert btc.mark_px == Decimal("100000")
    assert btc.open_interest == Decimal("12.5")
    assert btc.open_interest_usd == Decimal("1250000")
    assert ctxs[1].funding == Decimal("-0.00002")


@respx.mock
def test_network_error_yields_empty_no_crash() -> None:
    respx.post(f"{_BASE}/info").mock(side_effect=httpx.ConnectError("boom"))
    assert _cli().get_asset_contexts() == []


@respx.mock
def test_unexpected_shape_yields_empty() -> None:
    respx.post(f"{_BASE}/info").mock(return_value=httpx.Response(200, json={"unexpected": True}))
    assert _cli().get_asset_contexts() == []


@respx.mock
def test_skips_rows_with_bad_prices() -> None:
    respx.post(f"{_BASE}/info").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"universe": [{"name": "BAD"}, {"name": "ETH"}]},
                [
                    {"markPx": "0", "oraclePx": "0"},
                    {
                        "markPx": "3000",
                        "oraclePx": "2999",
                        "openInterest": "50",
                        "funding": "0.00001",
                        "dayNtlVlm": "10000000",
                    },
                ],
            ],
        )
    )
    ctxs = _cli().get_asset_contexts()
    assert [c.coin for c in ctxs] == ["ETH"]
