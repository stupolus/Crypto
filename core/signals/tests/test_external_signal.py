"""Тесты переноса сигнала база→перп (план 27 фаза 27.1)."""

from __future__ import annotations

import httpx
import respx

from core.signals.external_signal import (
    SignalDirection,
    SignalProvider,
    TsmomSignalProvider,
    map_perp_to_underlying,
)

_GC = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F"
_MONTH_S = 30 * 24 * 3600


def _resp(closes: list[float]) -> httpx.Response:
    base = 1_420_070_400
    ts = [base + i * _MONTH_S for i in range(len(closes))]
    return httpx.Response(
        200,
        json={
            "chart": {"result": [{"timestamp": ts, "indicators": {"quote": [{"close": closes}]}}]}
        },
    )


def test_map_perp_to_underlying() -> None:
    assert map_perp_to_underlying("XAUT-USDT") == "GC=F"
    assert map_perp_to_underlying("BTC-USDT") is None


def test_protocol_runtime_check() -> None:
    assert isinstance(TsmomSignalProvider(), SignalProvider)


@respx.mock
def test_long_when_underlying_up_over_lookback() -> None:
    closes = [100.0 + i for i in range(20)]  # монотонный рост
    respx.get(_GC).mock(return_value=_resp(closes))
    p = TsmomSignalProvider(client=httpx.Client(), backoff=0.0)
    assert p.direction("XAUT-USDT", 0) is SignalDirection.LONG


@respx.mock
def test_short_when_underlying_down_over_lookback() -> None:
    closes = [200.0 - i * 3 for i in range(20)]
    respx.get(_GC).mock(return_value=_resp(closes))
    p = TsmomSignalProvider(client=httpx.Client(), backoff=0.0)
    assert p.direction("XAUT-USDT", 0) is SignalDirection.SHORT


def test_unsupported_perp_is_flat() -> None:
    p = TsmomSignalProvider(client=httpx.Client(), backoff=0.0)
    assert p.direction("BTC-USDT", 0) is SignalDirection.FLAT


@respx.mock
def test_yahoo_blocked_is_flat_no_crash() -> None:
    respx.get(_GC).mock(return_value=httpx.Response(429, text="rate"))
    p = TsmomSignalProvider(client=httpx.Client(), backoff=0.0)
    assert p.direction("XAUT-USDT", 0) is SignalDirection.FLAT
