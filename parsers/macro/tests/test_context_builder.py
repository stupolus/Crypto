"""Unit-тесты ``MacroContextBuilder``."""

from __future__ import annotations

from decimal import Decimal

import pytest

from parsers.macro import (
    FREDAdapter,
    MacroContextBuilder,
    YfinanceAdapter,
    YfinanceQuote,
)


class _MockYahoo:
    def __init__(self, quotes: dict[str, YfinanceQuote] | None = None) -> None:
        self._quotes = quotes or {}
        self.call_count = 0

    def fetch(self, tickers: list[str]) -> dict[str, YfinanceQuote]:
        self.call_count += 1
        return {t: self._quotes[t] for t in tickers if t in self._quotes}


class _MockFRED:
    def __init__(self, observations: dict[str, Decimal] | None = None) -> None:
        self._obs = observations or {}
        self.call_count = 0

    def fetch_latest(self, series_ids: list[str]) -> dict[str, Decimal]:
        self.call_count += 1
        return {s: self._obs[s] for s in series_ids if s in self._obs}


def _build(
    yf_quotes: dict[str, YfinanceQuote] | None = None,
    fred_obs: dict[str, Decimal] | None = None,
    cache_ttl_s: float = 3600.0,
) -> tuple[MacroContextBuilder, _MockYahoo, _MockFRED]:
    yf_mock = _MockYahoo(yf_quotes)
    fred_mock = _MockFRED(fred_obs)
    builder = MacroContextBuilder(
        yfinance_adapter=YfinanceAdapter(fetcher=yf_mock),
        fred_adapter=FREDAdapter(fetcher=fred_mock),
        cache_ttl_s=cache_ttl_s,
    )
    return builder, yf_mock, fred_mock


def _quote(symbol: str, last: str, change: str = "0.0") -> YfinanceQuote:
    return YfinanceQuote(
        symbol=symbol,
        timestamp_ms=1_700_000_000_000,
        last=Decimal(last),
        change_pct_24h=Decimal(change),
    )


@pytest.mark.asyncio
async def test_context_builder_combines_yf_and_fred() -> None:
    builder, _, _ = _build(
        yf_quotes={
            "DX-Y.NYB": _quote("DX-Y.NYB", "104.5", "0.3"),
            "^VIX": _quote("^VIX", "18.2"),
            "^GSPC": _quote("^GSPC", "4500"),
            "^NDX": _quote("^NDX", "16000"),
            "GC=F": _quote("GC=F", "2050"),
            "CL=F": _quote("CL=F", "75"),
            "^TNX": _quote("^TNX", "4.25"),
        },
        fred_obs={
            "DFF": Decimal("5.33"),
            "UNRATE": Decimal("3.8"),
        },
    )
    ctx = await builder.build(btc_dominance_pct="52.5")
    assert ctx.dxy == "104.5"
    assert ctx.dxy_change_24h_pct == "0.3"
    assert ctx.vix == "18.2"
    assert ctx.spx == "4500"
    assert ctx.ndx == "16000"
    assert ctx.gold == "2050"
    assert ctx.oil == "75"
    assert ctx.yield_10y == "4.25"
    assert ctx.btc_dominance_pct == "52.5"


@pytest.mark.asyncio
async def test_context_builder_caches_result() -> None:
    """Второй call в TTL не дёргает adapters."""
    builder, yf_mock, fred_mock = _build(
        yf_quotes={"DX-Y.NYB": _quote("DX-Y.NYB", "104.0")},
        cache_ttl_s=3600.0,
    )
    ctx1 = await builder.build()
    ctx2 = await builder.build()
    assert ctx1 == ctx2
    assert yf_mock.call_count == 1
    assert fred_mock.call_count == 1


@pytest.mark.asyncio
async def test_context_builder_invalidate_cache() -> None:
    """invalidate_cache() заставляет refresh."""
    builder, yf_mock, _ = _build(
        yf_quotes={"DX-Y.NYB": _quote("DX-Y.NYB", "104.0")},
    )
    await builder.build()
    builder.invalidate_cache()
    await builder.build()
    assert yf_mock.call_count == 2


@pytest.mark.asyncio
async def test_context_builder_handles_missing_data() -> None:
    """Если yfinance вернул пусто — все макро-поля '0' (defaults)."""
    builder, _, _ = _build()  # пустые мoки
    ctx = await builder.build()
    assert ctx.dxy == "0"
    assert ctx.vix == "0"
    # Не падает, builder возвращает defaults


@pytest.mark.asyncio
async def test_context_builder_partial_data() -> None:
    """Часть полей есть, часть нет — корректно обрабатываем."""
    builder, _, _ = _build(
        yf_quotes={
            "DX-Y.NYB": _quote("DX-Y.NYB", "104.5"),
            # остальные отсутствуют
        },
    )
    ctx = await builder.build()
    assert ctx.dxy == "104.5"
    assert ctx.vix == "0"
    assert ctx.spx == "0"


@pytest.mark.asyncio
async def test_context_builder_cache_expires() -> None:
    """После TTL — refresh."""
    builder, yf_mock, _ = _build(
        yf_quotes={"DX-Y.NYB": _quote("DX-Y.NYB", "104.0")},
        cache_ttl_s=0.0001,  # TTL почти ноль
    )
    await builder.build()
    import asyncio

    await asyncio.sleep(0.01)
    await builder.build()
    assert yf_mock.call_count == 2
