"""Unit-тесты ``status_event_stream`` + ``/stream/events`` endpoint."""

from __future__ import annotations

import json
import pathlib
from decimal import Decimal

import pytest

from core.dashboard.api import create_app
from core.dashboard.sse import _build_status_payload, status_event_stream
from core.dashboard.state import DashboardState
from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import DecisionContext


def _seed(db: pathlib.Path) -> None:
    log = TradeOutcomeLogger(db)
    log.record_entry(
        DecisionContext(
            trade_id="open1",
            symbol="BTC-USDT",
            side="BUY",
            entry_time_ms=1_700_000_000_000,
            entry_price=Decimal("80500"),
            size=Decimal("0.1"),
            signal_candidate={"action": "BUY"},
            market_analyst={"state": "TRENDING_UP"},
            sentiment_analyst={"sentiment_score": 0.4},
            risk_overseer={"approved": True},
            macro_analyst={"regime": "RISK_ON"},
            coordinator={"action": "BUY", "composite_confidence": 0.7},
        )
    )


def test_build_status_payload_shape(tmp_path: pathlib.Path) -> None:
    db = tmp_path / "x.sqlite"
    _seed(db)
    state = DashboardState(outcomes_db=db, halt_flag_file=None, heartbeat_file=None)
    payload = _build_status_payload(state)
    assert "health" in payload
    assert "trades" in payload
    assert payload["trades"]["total"] == 1
    assert payload["trades"]["open"] == 1


@pytest.mark.asyncio
async def test_status_event_stream_yields_status(tmp_path: pathlib.Path) -> None:
    """Async gen эмитит первое событие сразу + правильный SSE формат."""
    db = tmp_path / "x.sqlite"
    _seed(db)
    state = DashboardState(outcomes_db=db, halt_flag_file=None, heartbeat_file=None)

    gen = status_event_stream(state, interval_s=0.05)
    first = await gen.__anext__()
    assert first.startswith("retry:")

    second = await gen.__anext__()
    assert "event: status" in second
    # Extract JSON
    data_line = next(line for line in second.split("\n") if line.startswith("data: "))
    parsed = json.loads(data_line[len("data: ") :])
    assert "trades" in parsed
    await gen.aclose()


@pytest.mark.asyncio
async def test_stream_yields_keepalive_heartbeat(tmp_path: pathlib.Path) -> None:
    """Проверяем что async gen эмитит valid SSE формат с retry + event."""
    db = tmp_path / "x.sqlite"
    _seed(db)
    state = DashboardState(outcomes_db=db, halt_flag_file=None, heartbeat_file=None)

    gen = status_event_stream(state, interval_s=0.01)
    # Берём 5 events максимум, потом aclose
    chunks: list[str] = []
    for _ in range(3):
        chunks.append(await gen.__anext__())
    await gen.aclose()

    # Первый — retry directive
    assert chunks[0].startswith("retry:")
    # Остальные — event: status
    for c in chunks[1:]:
        assert "event: status" in c
        assert "data:" in c


def test_create_app_registers_stream_route(tmp_path: pathlib.Path) -> None:
    """SSE endpoint зарегистрирован в FastAPI."""
    app = create_app(outcomes_db=tmp_path / "x.sqlite", halt_flag_file=None, heartbeat_file=None)
    routes = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/stream/events" in routes
