"""Unit-тесты helper'ов ``runners.llm_runner``.

Полный orchestrator (``run()``) тестируется на VST в integration-наборе.
Здесь — изолированные unit-тесты для конвертеров и stub-фетчеров.
"""

from __future__ import annotations

from decimal import Decimal

from adapters.bingx.models import Kline
from adapters.bingx.private_models import OrderRequest
from core.agents.llm_gate import LLMGateResult
from core.agents.team import TeamDecision
from core.backtest.models import OpenPosition
from runners.live_runner import RunnerState
from runners.llm_runner import (
    _build_decision_context,
    _build_runner_state_snapshot,
    _NoopFREDFetcher,
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


def test_noop_fred_fetcher_returns_empty() -> None:
    fetcher = _NoopFREDFetcher()
    assert fetcher.fetch_latest(["DFF", "UNRATE"]) == {}


def test_noop_fred_satisfies_protocol() -> None:
    """Проверяем что NoopFREDFetcher работает в FREDAdapter."""
    from parsers.macro.fred_adapter import FREDAdapter

    adapter = FREDAdapter(fetcher=_NoopFREDFetcher())
    snap = adapter.snapshot()
    assert snap.fed_funds_rate is None
    assert snap.cpi_urban is None
    # Warnings про отсутствие каждой series
    assert len(snap.warnings) >= 4


def _make_candle(close: str = "80500") -> Kline:
    return Kline.model_validate(
        {
            "time": 1_700_000_000_000,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": "1",
        }
    )


def _make_approved_request() -> OrderRequest:
    return OrderRequest(
        symbol="BTC-USDT",
        side="BUY",
        position_side="LONG",
        order_type="LIMIT",
        quantity=Decimal("0.1"),
        price=Decimal("80500"),
        attached_stop_loss=Decimal("80000"),
        attached_take_profit=Decimal("82000"),
    )


def _make_gate_result(action: str = "BUY") -> LLMGateResult:
    decision = TeamDecision(
        coordinator_payload={
            "action": action,
            "size_risk_pct": 1.0,
            "composite_confidence": 0.75,
        },
        subagent_payloads={
            "market": {"state": "TRENDING_UP"},
            "sentiment": {"sentiment_score": 0.4},
            "risk": {"approved": True},
            "macro": {"regime": "RISK_ON"},
        },
        macro_cached=False,
        total_latency_ms=350,
        total_cost_usd=0.05,
    )
    return LLMGateResult(
        approved_request=_make_approved_request(),
        decision=decision,
        reason="APPROVED",
    )


def test_build_decision_context_pulls_all_payloads() -> None:
    ctx = _build_decision_context(
        trade_id="bingx_order_42",
        approved=_make_approved_request(),
        gate_result=_make_gate_result(),
        candle=_make_candle(),
    )
    assert ctx.trade_id == "bingx_order_42"
    assert ctx.symbol == "BTC-USDT"
    assert ctx.side == "BUY"
    assert ctx.entry_price == Decimal("80500")
    assert ctx.size == Decimal("0.1")
    # LLM payloads разобраны
    assert ctx.market_analyst == {"state": "TRENDING_UP"}
    assert ctx.coordinator["action"] == "BUY"
    assert ctx.coordinator["composite_confidence"] == 0.75
    assert ctx.latency_decision_ms == 350


def test_build_decision_context_market_order_uses_candle_close() -> None:
    """MARKET order не имеет price → entry_price берётся из candle.close."""
    market_request = OrderRequest(
        symbol="BTC-USDT",
        side="BUY",
        position_side="LONG",
        order_type="MARKET",
        quantity=Decimal("0.1"),
        attached_stop_loss=Decimal("80000"),
    )
    ctx = _build_decision_context(
        trade_id="t1",
        approved=market_request,
        gate_result=_make_gate_result(),
        candle=_make_candle(close="80600"),
    )
    assert ctx.entry_price == Decimal("80600")


def test_equity_snapshot_loop_writes_jsonl(tmp_path: object) -> None:
    """_equity_snapshot_loop пишет {timestamp_ms, equity} и завершается по stop_event."""
    import asyncio
    import json
    from pathlib import Path
    from unittest.mock import AsyncMock

    from runners.llm_runner import _equity_snapshot_loop

    snap = Path(tmp_path) / "equity.jsonl"  # type: ignore[arg-type]
    fake_api = AsyncMock()
    fake_api.get_balance.return_value = []  # _fetch_equity → Decimal("0")

    async def _run() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(_equity_snapshot_loop(snap, fake_api, stop, interval_s=0.05))
        await asyncio.sleep(0.12)  # ~2 итерации
        stop.set()
        await asyncio.wait_for(task, timeout=1.0)

    asyncio.run(_run())
    assert snap.exists()
    lines = [ln for ln in snap.read_text().splitlines() if ln.strip()]
    assert len(lines) >= 1
    rec = json.loads(lines[0])
    assert "timestamp_ms" in rec
    assert "equity" in rec
