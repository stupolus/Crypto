"""Тесты сезонность+режим (план 24 фаза 24.1)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import respx

from parsers.macro.seasonality import (
    MarketRegime,
    MonthBias,
    compute_month_stats,
    market_regime,
    month_bias,
    regime_history,
)

_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/AAPL"
_IDX = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC"


def _monthly_response(closes: list[float], *, start_year: int = 2014) -> httpx.Response:
    ts = [
        int(datetime(start_year + i // 12, i % 12 + 1, 1, tzinfo=UTC).timestamp())
        for i in range(len(closes))
    ]
    return httpx.Response(
        200,
        json={
            "chart": {"result": [{"timestamp": ts, "indicators": {"quote": [{"close": closes}]}}]}
        },
    )


@respx.mock
def test_september_bear_july_bull() -> None:
    # 11 лет: сентябрь всегда −5%, июль всегда +8%, прочее +0.5%.
    closes = [100.0]
    for i in range(1, 132):
        month = i % 12 + 1
        if month == 9:
            closes.append(closes[-1] * 0.95)
        elif month == 7:
            closes.append(closes[-1] * 1.08)
        else:
            closes.append(closes[-1] * 1.005)
    respx.get(_CHART).mock(return_value=_monthly_response(closes))
    stats = compute_month_stats("AAPL", client=httpx.Client(), backoff=0.0)
    assert stats[9].win_rate == 0.0
    assert stats[7].win_rate == 1.0
    assert month_bias(stats, 9) is MonthBias.BEAR
    assert month_bias(stats, 7) is MonthBias.BULL


def test_month_bias_neutral_and_low_samples() -> None:
    from parsers.macro.seasonality import MonthStat

    mixed = {5: MonthStat(month=5, avg_return_pct=0.3, win_rate=0.55, samples=10)}
    assert month_bias(mixed, 5) is MonthBias.NEUTRAL
    thin = {5: MonthStat(month=5, avg_return_pct=9.0, win_rate=1.0, samples=3)}
    assert month_bias(thin, 5) is MonthBias.NEUTRAL
    assert month_bias({}, 1) is MonthBias.NEUTRAL


@respx.mock
def test_blocked_yahoo_yields_empty_and_neutral() -> None:
    respx.get(_CHART).mock(return_value=httpx.Response(429, text="rate"))
    stats = compute_month_stats("AAPL", client=httpx.Client(), backoff=0.0)
    assert stats == {}
    assert month_bias(stats, 9) is MonthBias.NEUTRAL


@respx.mock
def test_market_regime_risk_on_off() -> None:
    respx.get(_IDX).mock(return_value=_monthly_response([100.0 + i for i in range(36)]))
    assert market_regime("^GSPC", client=httpx.Client(), backoff=0.0) is MarketRegime.RISK_ON
    respx.get(_IDX).mock(return_value=_monthly_response([200.0 - i * 3 for i in range(36)]))
    assert market_regime("^GSPC", client=httpx.Client(), backoff=0.0) is MarketRegime.RISK_OFF


@respx.mock
def test_regime_unknown_when_blocked() -> None:
    respx.get(_IDX).mock(side_effect=httpx.ConnectError("boom"))
    assert market_regime("^GSPC", client=httpx.Client(), backoff=0.0) is MarketRegime.UNKNOWN


@respx.mock
def test_regime_history_lookahead_safe() -> None:
    closes = [100.0 + i * 2 for i in range(12)] + [124.0 - i * 5 for i in range(12)]
    respx.get(_IDX).mock(return_value=_monthly_response(closes, start_year=2015))
    hist = regime_history("^GSPC", client=httpx.Client(), backoff=0.0)
    assert hist
    assert hist[(2015, 12)] is MarketRegime.RISK_ON
    assert hist[(2016, 12)] is MarketRegime.RISK_OFF


@respx.mock
def test_regime_history_empty_when_blocked() -> None:
    respx.get(_IDX).mock(return_value=httpx.Response(429, text="rate"))
    assert regime_history("^GSPC", client=httpx.Client(), backoff=0.0) == {}
