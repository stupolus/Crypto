"""Unit-тесты ``YfinanceAdapter``.

Используем mock fetcher, не реальный yfinance — не зависим от сети.
"""

from __future__ import annotations

from decimal import Decimal

from parsers.macro import MacroSnapshot, YahooFetcher, YfinanceAdapter, YfinanceQuote


class _MockFetcher:
    """Mock fetcher с настраиваемым response. Реализует YahooFetcher Protocol."""

    def __init__(
        self,
        quotes: dict[str, YfinanceQuote] | None = None,
        raise_exception: Exception | None = None,
    ) -> None:
        self._quotes = quotes or {}
        self._raise = raise_exception

    def fetch(self, tickers: list[str]) -> dict[str, YfinanceQuote]:
        if self._raise:
            raise self._raise
        return {t: self._quotes[t] for t in tickers if t in self._quotes}


def _make_quote(symbol: str, last: str, change: str = "0.0") -> YfinanceQuote:
    return YfinanceQuote(
        symbol=symbol,
        timestamp_ms=1_700_000_000_000,
        last=Decimal(last),
        change_pct_24h=Decimal(change),
    )


def test_yfinance_adapter_full_snapshot() -> None:
    fetcher = _MockFetcher(
        quotes={
            "DX-Y.NYB": _make_quote("DX-Y.NYB", "104.5", "0.3"),
            "^VIX": _make_quote("^VIX", "18.2", "-2.1"),
            "^GSPC": _make_quote("^GSPC", "4500"),
            "^NDX": _make_quote("^NDX", "16000"),
            "GC=F": _make_quote("GC=F", "2050"),
            "CL=F": _make_quote("CL=F", "75"),
            "^TNX": _make_quote("^TNX", "4.25"),
        }
    )
    adapter = YfinanceAdapter(fetcher=fetcher)
    snap = adapter.snapshot()
    assert isinstance(snap, MacroSnapshot)
    assert snap.dxy == Decimal("104.5")
    assert snap.dxy_change_24h_pct == Decimal("0.3")
    assert snap.vix == Decimal("18.2")
    assert snap.spx == Decimal("4500")
    assert snap.ndx == Decimal("16000")
    assert snap.gold == Decimal("2050")
    assert snap.oil == Decimal("75")
    assert snap.yield_10y == Decimal("4.25")
    assert snap.warnings == ()


def test_yfinance_adapter_partial_snapshot() -> None:
    """Если только часть тикеров доступна — остальные None, warnings."""
    fetcher = _MockFetcher(
        quotes={
            "DX-Y.NYB": _make_quote("DX-Y.NYB", "104.5"),
            "^VIX": _make_quote("^VIX", "18.2"),
            # остальные отсутствуют
        }
    )
    adapter = YfinanceAdapter(fetcher=fetcher)
    snap = adapter.snapshot()
    assert snap.dxy == Decimal("104.5")
    assert snap.spx is None
    assert snap.gold is None
    assert len(snap.warnings) > 0
    assert any("^GSPC" in w for w in snap.warnings)


def test_yfinance_adapter_fetch_failure_returns_empty_snapshot() -> None:
    """Если fetcher бросает — возвращаем пустой snapshot с warning."""
    fetcher = _MockFetcher(raise_exception=RuntimeError("Yahoo down"))
    adapter = YfinanceAdapter(fetcher=fetcher)
    snap = adapter.snapshot()
    assert snap.dxy is None
    assert snap.vix is None
    assert len(snap.warnings) == 1
    assert "Yahoo down" in snap.warnings[0]


def test_yahoo_fetcher_protocol_implements() -> None:
    """Сабмит что _MockFetcher удовлетворяет YahooFetcher Protocol."""
    fetcher: YahooFetcher = _MockFetcher()
    assert hasattr(fetcher, "fetch")


def test_yfinance_adapter_empty_response_warnings() -> None:
    """Если fetcher вернул {}, ВСЕ тикеры в warnings."""
    fetcher = _MockFetcher(quotes={})
    adapter = YfinanceAdapter(fetcher=fetcher)
    snap = adapter.snapshot()
    assert snap.dxy is None
    assert len(snap.warnings) == 7  # все 7 тикеров
