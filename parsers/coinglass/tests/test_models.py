"""Unit-тесты для ``parsers.coinglass.models``."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from parsers.coinglass.models import (
    CoinglassFundingPoint,
    CoinglassLiquidationCluster,
    CoinglassLiquidationHeatmap,
    CoinglassOIPoint,
)


def test_oi_point_basic() -> None:
    p = CoinglassOIPoint(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        open_interest_usd=Decimal("5000000000"),
        open_interest_change_24h_pct=Decimal("2.3"),
    )
    assert p.open_interest_usd == Decimal("5000000000")
    assert p.open_interest_change_24h_pct == Decimal("2.3")


def test_oi_point_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        CoinglassOIPoint(
            symbol="BTC-USDT",
            timestamp_ms=1_700_000_000_000,
            open_interest_usd=Decimal("-1"),
        )


def test_funding_point_basic() -> None:
    p = CoinglassFundingPoint(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        funding_rate_pct=Decimal("0.01"),
        next_funding_time_ms=1_700_028_800_000,
    )
    assert p.funding_rate_pct == Decimal("0.01")
    assert p.interval_hours == 8


def test_funding_point_invalid_interval() -> None:
    with pytest.raises(ValidationError):
        CoinglassFundingPoint(
            symbol="BTC-USDT",
            timestamp_ms=1_700_000_000_000,
            funding_rate_pct=Decimal("0.01"),
            interval_hours=0,
        )


def test_liquidation_cluster_side_validated() -> None:
    cluster = CoinglassLiquidationCluster(
        price_level=Decimal("82000"),
        volume_usd=Decimal("5000000"),
        side="long",
    )
    assert cluster.side == "long"

    with pytest.raises(ValidationError):
        CoinglassLiquidationCluster(
            price_level=Decimal("82000"),
            volume_usd=Decimal("5000000"),
            side="invalid",
        )


def test_heatmap_largest_clusters() -> None:
    heatmap = CoinglassLiquidationHeatmap(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        current_price=Decimal("80000"),
        clusters_above=(
            CoinglassLiquidationCluster(
                price_level=Decimal("81000"),
                volume_usd=Decimal("3000000"),
                side="short",
            ),
            CoinglassLiquidationCluster(
                price_level=Decimal("82500"),
                volume_usd=Decimal("8000000"),
                side="short",
            ),
        ),
        clusters_below=(
            CoinglassLiquidationCluster(
                price_level=Decimal("79000"),
                volume_usd=Decimal("4000000"),
                side="long",
            ),
        ),
    )
    assert heatmap.largest_above is not None
    assert heatmap.largest_above.price_level == Decimal("82500")
    assert heatmap.largest_below is not None
    assert heatmap.largest_below.price_level == Decimal("79000")


def test_heatmap_empty_returns_none() -> None:
    heatmap = CoinglassLiquidationHeatmap(
        symbol="BTC-USDT",
        timestamp_ms=1_700_000_000_000,
        current_price=Decimal("80000"),
    )
    assert heatmap.largest_above is None
    assert heatmap.largest_below is None
