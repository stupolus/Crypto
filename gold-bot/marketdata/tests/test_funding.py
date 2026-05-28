"""Тесты funding-модуля: пагинация, parquet roundtrip, выравнивание, статистика."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from marketdata.funding import (
    FundingRate,
    align_funding_pair,
    divergence_stats,
    download_funding_history,
    funding_path,
    load_parquet,
    save_parquet,
)


class FakeFundingSource:
    """Mock ccxt-like adapter: возвращает страницы funding-rate dict'ов."""

    def __init__(self, rates: list[dict[str, Any]], page_size: int = 3) -> None:
        self._all = sorted(rates, key=lambda r: r["timestamp"])
        self._page_size = page_size
        self.calls: list[tuple[int | None, int | None]] = []

    async def fetch_funding_rate_history(
        self, symbol: str, since: int | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append((since, limit))
        out = [r for r in self._all if since is None or r["timestamp"] >= since]
        return out[: (limit or self._page_size)]


async def test_download_funding_history_basic() -> None:
    src = FakeFundingSource(
        rates=[
            {"timestamp": 1_000, "fundingRate": 0.0001},
            {"timestamp": 28_800_000, "fundingRate": -0.0002},
            {"timestamp": 57_600_000, "fundingRate": 0.0003},
        ],
        page_size=10,
    )
    rates = await download_funding_history(src, "XAUT/USDT:USDT", start_ms=0)
    assert len(rates) == 3
    assert rates[0] == FundingRate(timestamp=1_000, rate=Decimal("0.0001"))
    assert rates[-1] == FundingRate(timestamp=57_600_000, rate=Decimal("0.0003"))


async def test_download_funding_history_pagination_and_dedup() -> None:
    # Маленький page_size заставляет вызывать API многократно
    src = FakeFundingSource(
        rates=[{"timestamp": i * 1000, "fundingRate": 0.0001 * (i + 1)} for i in range(8)],
        page_size=3,
    )
    rates = await download_funding_history(src, "X/Y:Y", start_ms=0, page_limit=3)
    assert len(rates) == 8
    # Несколько вызовов API
    assert len(src.calls) >= 2
    # Дедуп: timestamp всегда уникальны
    assert len({r.timestamp for r in rates}) == 8


async def test_download_funding_history_skips_none() -> None:
    # Биржа иногда возвращает entry с пустым fundingRate
    src = FakeFundingSource(
        rates=[
            {"timestamp": 1_000, "fundingRate": 0.0001},
            {"timestamp": 2_000, "fundingRate": None},
            {"timestamp": 3_000, "fundingRate": 0.0003},
        ],
    )
    rates = await download_funding_history(src, "X/Y:Y", start_ms=0)
    assert len(rates) == 2
    assert rates[0].rate == Decimal("0.0001")


async def test_download_funding_history_respects_end_ms() -> None:
    src = FakeFundingSource(
        rates=[{"timestamp": i * 1000, "fundingRate": 0.0001} for i in range(10)],
        page_size=100,
    )
    rates = await download_funding_history(src, "X/Y:Y", start_ms=0, end_ms=4_500)
    timestamps = [r.timestamp for r in rates]
    assert all(ts <= 4_500 for ts in timestamps)
    assert max(timestamps) == 4_000


def test_funding_path_normalizes_symbol(tmp_path: Path) -> None:
    p = funding_path(tmp_path, "bingx", "XAUT/USDT:USDT")
    assert p.name == "XAUT_USDT_USDT.parquet"
    assert p.parent.name == "bingx"
    assert p.parent.parent.name == "funding"


def test_save_load_parquet_roundtrip(tmp_path: Path) -> None:
    rates = [
        FundingRate(timestamp=1_000, rate=Decimal("0.0001")),
        FundingRate(timestamp=2_000, rate=Decimal("-0.0002")),
        FundingRate(timestamp=3_000, rate=Decimal("0.00015")),
    ]
    path = funding_path(tmp_path, "bingx", "X/Y:Y")
    save_parquet(rates, path)
    loaded = load_parquet(path)
    assert loaded == rates
    # Decimal сохранён точно (не float)
    assert isinstance(loaded[1].rate, Decimal)
    assert loaded[1].rate == Decimal("-0.0002")


def test_save_load_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.parquet"
    save_parquet([], path)
    assert load_parquet(path) == []


# ── align_funding_pair ──


def _r(ts: int, rate: str) -> FundingRate:
    return FundingRate(timestamp=ts, rate=Decimal(rate))


def test_align_exact_match() -> None:
    a = [_r(1_000, "0.01"), _r(2_000, "0.02"), _r(3_000, "0.03")]
    b = [_r(1_000, "0.011"), _r(2_000, "0.022"), _r(3_000, "0.033")]
    paired = align_funding_pair(a, b)
    assert len(paired) == 3
    for pa, pb in paired:
        assert pa.timestamp == pb.timestamp


def test_align_within_tolerance() -> None:
    # 5 секунд расхождения, tolerance 1 минута → матчится
    a = [_r(60_000, "0.01")]
    b = [_r(65_000, "0.02")]
    paired = align_funding_pair(a, b, tolerance_ms=60_000)
    assert len(paired) == 1


def test_align_outside_tolerance() -> None:
    # 2 минуты расхождения, tolerance 1 минута → не матчится
    a = [_r(60_000, "0.01")]
    b = [_r(180_000, "0.02")]
    paired = align_funding_pair(a, b, tolerance_ms=60_000)
    assert paired == []


def test_align_skips_unmatched_one_sided() -> None:
    # У a три точки, у b только одна совпадает
    a = [_r(1_000, "0.01"), _r(100_000, "0.02"), _r(200_000, "0.03")]
    b = [_r(100_500, "0.022")]
    paired = align_funding_pair(a, b, tolerance_ms=1_000)
    assert len(paired) == 1
    assert paired[0][0].timestamp == 100_000


def test_align_rejects_negative_tolerance() -> None:
    with pytest.raises(ValueError):
        align_funding_pair([], [], tolerance_ms=-1)


# ── divergence_stats ──


def test_divergence_stats_basic() -> None:
    paired = [
        (_r(1, "0.01"), _r(1, "0.011")),  # |Δ| = 0.001
        (_r(2, "0.02"), _r(2, "0.025")),  # |Δ| = 0.005
        (_r(3, "0.03"), _r(3, "0.028")),  # |Δ| = 0.002
    ]
    stats = divergence_stats(paired)
    assert stats["n"] == 3
    # медиана из [0.001, 0.002, 0.005] = 0.002
    assert stats["median_abs_diff"] == Decimal("0.002")
    assert stats["max_abs_diff"] == Decimal("0.005")


def test_divergence_stats_empty() -> None:
    stats = divergence_stats([])
    assert stats["n"] == 0
    assert stats["median_abs_diff"] == Decimal(0)


def test_divergence_stats_p90() -> None:
    # 10 пар: |Δ| от 0.001 до 0.010
    paired = [
        (_r(i, str(Decimal("0.0"))), _r(i, str(Decimal("0.001") * (i + 1)))) for i in range(10)
    ]
    stats = divergence_stats(paired)
    assert stats["n"] == 10
    # p90 индекс = 9 (last) → 0.010
    assert stats["p90_abs_diff"] == Decimal("0.010")
