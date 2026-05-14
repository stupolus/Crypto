"""Unit-тесты ``FREDAdapter``."""

from __future__ import annotations

from decimal import Decimal

from parsers.macro import FREDAdapter, FREDFetcher, FREDSnapshot


class _MockFREDFetcher:
    """Реализует FREDFetcher Protocol."""

    def __init__(
        self,
        observations: dict[str, Decimal] | None = None,
        raise_exception: Exception | None = None,
    ) -> None:
        self._obs = observations or {}
        self._raise = raise_exception

    def fetch_latest(self, series_ids: list[str]) -> dict[str, Decimal]:
        if self._raise:
            raise self._raise
        return {sid: self._obs[sid] for sid in series_ids if sid in self._obs}


def test_fred_adapter_full_snapshot() -> None:
    fetcher = _MockFREDFetcher(
        observations={
            "DFF": Decimal("5.33"),
            "CPIAUCSL": Decimal("315.5"),
            "UNRATE": Decimal("3.8"),
            "T10Y2Y": Decimal("0.42"),
        }
    )
    adapter = FREDAdapter(fetcher=fetcher)
    snap = adapter.snapshot()
    assert snap.fed_funds_rate == Decimal("5.33")
    assert snap.cpi_urban == Decimal("315.5")
    assert snap.unemployment_rate == Decimal("3.8")
    assert snap.yield_spread_10y_2y == Decimal("0.42")
    assert snap.warnings == ()


def test_fred_adapter_partial_snapshot() -> None:
    fetcher = _MockFREDFetcher(
        observations={
            "DFF": Decimal("5.33"),
            # missing CPI, UNRATE, T10Y2Y
        }
    )
    adapter = FREDAdapter(fetcher=fetcher)
    snap = adapter.snapshot()
    assert snap.fed_funds_rate == Decimal("5.33")
    assert snap.cpi_urban is None
    assert snap.unemployment_rate is None
    assert len(snap.warnings) == 3
    assert any("CPIAUCSL" in w for w in snap.warnings)


def test_fred_adapter_fetch_failure() -> None:
    fetcher = _MockFREDFetcher(raise_exception=ConnectionError("FRED API down"))
    adapter = FREDAdapter(fetcher=fetcher)
    snap = adapter.snapshot()
    assert snap.fed_funds_rate is None
    assert snap.cpi_urban is None
    assert len(snap.warnings) == 1
    assert "FRED API down" in snap.warnings[0]


def test_fred_adapter_empty_response() -> None:
    fetcher = _MockFREDFetcher(observations={})
    adapter = FREDAdapter(fetcher=fetcher)
    snap = adapter.snapshot()
    assert snap.fed_funds_rate is None
    assert len(snap.warnings) == 4  # все 4 series


def test_fred_snapshot_equality() -> None:
    a = FREDSnapshot(fed_funds_rate=Decimal("5.0"))
    b = FREDSnapshot(fed_funds_rate=Decimal("5.0"))
    c = FREDSnapshot(fed_funds_rate=Decimal("4.5"))
    assert a == b
    assert a != c


def test_fred_snapshot_repr() -> None:
    snap = FREDSnapshot(fed_funds_rate=Decimal("5.33"))
    r = repr(snap)
    assert "FREDSnapshot" in r
    assert "5.33" in r


def test_fred_fetcher_protocol_compliance() -> None:
    fetcher: FREDFetcher = _MockFREDFetcher()
    assert hasattr(fetcher, "fetch_latest")
