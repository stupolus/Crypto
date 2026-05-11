"""Unit-тесты ``adapters.bingx.metrics``."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from adapters.bingx.metrics import (
    MetricsWriter,
    OrderMetric,
    compute_slippage_bps,
    now_ms,
)


def test_slippage_buy_higher_avg_is_positive_bps() -> None:
    # BUY и avg выше mark → slippage положительный = хуже для нас.
    s = compute_slippage_bps(
        side="BUY",
        request_mark_price=Decimal("60000"),
        ack_avg_price=Decimal("60030"),
    )
    assert s is not None
    # 30 / 60000 * 10000 = 5 bps
    assert s == Decimal("5.0000")


def test_slippage_sell_lower_avg_is_positive_bps() -> None:
    # SELL и avg ниже mark → slippage положительный (для нас хуже).
    s = compute_slippage_bps(
        side="SELL",
        request_mark_price=Decimal("60000"),
        ack_avg_price=Decimal("59970"),
    )
    assert s is not None
    assert s == Decimal("5.0000")


def test_slippage_returns_none_without_inputs() -> None:
    assert compute_slippage_bps("BUY", None, Decimal("60000")) is None
    assert compute_slippage_bps("BUY", Decimal("60000"), None) is None
    assert compute_slippage_bps("BUY", Decimal("0"), Decimal("60000")) is None


@pytest.mark.asyncio
async def test_metrics_writer_appends_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "metrics.jsonl"
    writer = MetricsWriter(path)
    metric = OrderMetric(
        client_order_id="abc",
        symbol="BTC-USDT",
        side="BUY",
        type="MARKET",
        request_started_ms=now_ms(),
        ack_received_ms=now_ms() + 250,
        latency_ms=250,
        ack_status="FILLED",
        request_mark_price=Decimal("60000"),
        ack_avg_price=Decimal("60030"),
        slippage_bps=Decimal("5.0"),
    )
    await writer.record(metric)
    await writer.record(metric)
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    parsed = json.loads(lines[0])
    assert parsed["symbol"] == "BTC-USDT"
    assert parsed["latency_ms"] == 250
    assert parsed["slippage_bps"] == "5"
