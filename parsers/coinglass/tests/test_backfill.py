"""Тесты Coinglass backfill → Static-провайдеры (план 21.4)."""

from __future__ import annotations

from decimal import Decimal

import httpx
import respx

from core.signals import StaticLiquidationProvider, StaticOpenInterestProvider
from parsers.coinglass.backfill import backfill_providers, map_symbol
from parsers.coinglass.client import CoinglassClient

_BASE = "https://open-api-v4.coinglass.com"


def _cg() -> CoinglassClient:
    return CoinglassClient(api_key="k", client=httpx.Client(base_url=_BASE))


def test_map_symbol() -> None:
    assert map_symbol("BTC-USDT") == ("Binance", "BTCUSDT", "BTC")
    assert map_symbol("ETH-USDT") == ("Binance", "ETHUSDT", "ETH")
    assert map_symbol("XAUT-USDT") is None


def test_unknown_symbol_returns_empty_providers() -> None:
    liq, oi, delta = backfill_providers(
        "XAUT-USDT", "4h", start_time_ms=0, end_time_ms=1, client=_cg()
    )
    assert isinstance(liq, StaticLiquidationProvider)
    assert isinstance(oi, StaticOpenInterestProvider)
    assert liq.get_bucket("XAUT-USDT", 0) is None
    assert oi.get_series("XAUT-USDT", 999, 5) == []
    assert delta.get_cvd_series("XAUT-USDT", 999, 5) == []


@respx.mock
def test_backfill_populates_providers() -> None:
    respx.get(f"{_BASE}/api/futures/liquidation/history").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "0",
                "data": [
                    {"time": 1000, "long_liquidation_usd": "50000", "short_liquidation_usd": "0"},
                    {"time": 2000, "long_liquidation_usd": "0", "short_liquidation_usd": "30000"},
                ],
            },
        )
    )
    respx.get(f"{_BASE}/api/futures/open-interest/aggregated-history").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "0",
                "data": [
                    {"time": 1000, "close": "5000000"},
                    {"time": 2000, "close": "5100000"},
                ],
            },
        )
    )
    respx.get(f"{_BASE}/api/futures/taker-buy-sell-volume/history").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": "0",
                "data": [
                    {"time": 1000, "taker_buy_volume_usd": "100", "taker_sell_volume_usd": "40"},
                    {"time": 2000, "taker_buy_volume_usd": "10", "taker_sell_volume_usd": "70"},
                ],
            },
        )
    )
    liq, oi, delta = backfill_providers(
        "BTC-USDT", "4h", start_time_ms=0, end_time_ms=9999, client=_cg()
    )
    b = liq.get_bucket("BTC-USDT", 1000)
    assert b is not None and b.long_volume == Decimal("50000")
    assert oi.get_series("BTC-USDT", 2000, 5) == [Decimal("5000000"), Decimal("5100000")]
    # CVD кумулятивный: bar1 +60, bar2 +(10-70)=-60 → [60, 0]
    assert delta.get_cvd_series("BTC-USDT", 2000, 5) == [Decimal("60"), Decimal("0")]


@respx.mock
def test_plan_inactive_yields_empty_but_no_crash() -> None:
    respx.get(f"{_BASE}/api/futures/liquidation/history").mock(
        return_value=httpx.Response(200, json={"code": "401", "msg": "Upgrade plan"})
    )
    respx.get(f"{_BASE}/api/futures/open-interest/aggregated-history").mock(
        return_value=httpx.Response(200, json={"code": "401", "msg": "Upgrade plan"})
    )
    respx.get(f"{_BASE}/api/futures/taker-buy-sell-volume/history").mock(
        return_value=httpx.Response(200, json={"code": "401", "msg": "Upgrade plan"})
    )
    liq, oi, delta = backfill_providers(
        "BTC-USDT", "4h", start_time_ms=0, end_time_ms=9999, client=_cg()
    )
    assert liq.get_bucket("BTC-USDT", 1000) is None
    assert oi.get_series("BTC-USDT", 9999, 5) == []
    assert delta.get_cvd_series("BTC-USDT", 9999, 5) == []


@respx.mock
def test_pagination_multi_window() -> None:
    """4h-интервал → пагинация: 2 окна склеиваются, дедуп по ts."""
    _4H = 4 * 3_600_000
    t0 = 1_700_000_000_000  # реалистичный epoch-ms (ts > 0)
    calls = {"liq": 0}

    def _liq(request: httpx.Request) -> httpx.Response:
        calls["liq"] += 1
        if calls["liq"] == 1:
            data = [
                {"time": t0, "long_liquidation_usd": "1", "short_liquidation_usd": "0"},
                {"time": t0 + _4H, "long_liquidation_usd": "2", "short_liquidation_usd": "0"},
            ]
        else:
            data = [
                {"time": t0 + _4H, "long_liquidation_usd": "2", "short_liquidation_usd": "0"},
                {"time": t0 + 2 * _4H, "long_liquidation_usd": "3", "short_liquidation_usd": "0"},
            ]
        return httpx.Response(200, json={"code": "0", "data": data})

    respx.get(f"{_BASE}/api/futures/liquidation/history").mock(side_effect=_liq)
    respx.get(f"{_BASE}/api/futures/open-interest/aggregated-history").mock(
        return_value=httpx.Response(200, json={"code": "0", "data": []})
    )
    respx.get(f"{_BASE}/api/futures/taker-buy-sell-volume/history").mock(
        return_value=httpx.Response(200, json={"code": "0", "data": []})
    )
    liq, _oi, _delta = backfill_providers(
        "BTC-USDT", "4h", start_time_ms=t0, end_time_ms=t0 + 3 * _4H, client=_cg()
    )
    # 3 уникальных ts — t0+4h дедуплицирован между окнами
    assert liq.get_bucket("BTC-USDT", t0) is not None
    assert liq.get_bucket("BTC-USDT", t0 + _4H) is not None
    assert liq.get_bucket("BTC-USDT", t0 + 2 * _4H) is not None
    assert calls["liq"] >= 2  # реально было >1 окна
