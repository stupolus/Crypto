"""Unit-тесты helper'ов ``runners.llm_runner``.

Полный orchestrator (``run()``) тестируется на VST в integration-наборе.
Здесь — изолированные unit-тесты для конвертеров и stub-фетчеров.
"""

from __future__ import annotations

from decimal import Decimal

from core.backtest.models import OpenPosition
from runners.live_runner import RunnerState
from runners.llm_runner import (
    _build_runner_state_snapshot,
    _NoopFREDFetcher,
    _NoopYahooFetcher,
)


def test_build_snapshot_without_position() -> None:
    state = RunnerState(
        candles_history=[],
        open_position=None,
        equity=Decimal("1234.5"),
    )
    snap = _build_runner_state_snapshot(state)
    assert snap.equity == Decimal("1234.5")
    assert snap.daily_pnl_pct == Decimal("0")
    assert snap.open_positions == ()


def test_build_snapshot_with_position() -> None:
    state = RunnerState(
        candles_history=[],
        open_position=OpenPosition(
            entry_price=Decimal("80500"),
            quantity=Decimal("0.1"),
            side="BUY",
            stop_price=Decimal("80000"),
            take_profit_price=Decimal("82000"),
            entry_time_ms=1_700_000_000_000,
        ),
        equity=Decimal("1000"),
    )
    snap = _build_runner_state_snapshot(state)
    assert len(snap.open_positions) == 1
    pos = snap.open_positions[0]
    assert pos["side"] == "BUY"
    assert pos["entry_price"] == "80500"
    assert pos["quantity"] == "0.1"
    assert pos["stop_price"] == "80000"
    assert pos["take_profit_price"] == "82000"


def test_build_snapshot_with_position_no_tp() -> None:
    state = RunnerState(
        candles_history=[],
        open_position=OpenPosition(
            entry_price=Decimal("80500"),
            quantity=Decimal("0.1"),
            side="BUY",
            stop_price=Decimal("80000"),
            take_profit_price=None,
            entry_time_ms=1_700_000_000_000,
        ),
        equity=Decimal("1000"),
    )
    snap = _build_runner_state_snapshot(state)
    assert snap.open_positions[0]["take_profit_price"] == "0"


def test_noop_yahoo_fetcher_returns_empty() -> None:
    fetcher = _NoopYahooFetcher()
    assert fetcher.fetch(["DX-Y.NYB", "^VIX"]) == {}


def test_noop_fred_fetcher_returns_empty() -> None:
    fetcher = _NoopFREDFetcher()
    assert fetcher.fetch_latest(["DFF", "UNRATE"]) == {}


def test_noop_yahoo_satisfies_protocol() -> None:
    """Проверяем что NoopYahooFetcher используется в YfinanceAdapter без ошибок."""
    from parsers.macro.yfinance_adapter import YfinanceAdapter

    adapter = YfinanceAdapter(fetcher=_NoopYahooFetcher())
    snap = adapter.snapshot()
    # Все поля будут None (warning'и про отсутствие тикеров)
    assert snap.dxy is None
    assert snap.vix is None
    assert len(snap.warnings) > 0


def test_noop_fred_satisfies_protocol() -> None:
    """Проверяем что NoopFREDFetcher работает в FREDAdapter."""
    from parsers.macro.fred_adapter import FREDAdapter

    adapter = FREDAdapter(fetcher=_NoopFREDFetcher())
    snap = adapter.snapshot()
    assert snap.fed_funds_rate is None
    assert snap.cpi_urban is None
    # Warnings про отсутствие каждой series
    assert len(snap.warnings) >= 4
