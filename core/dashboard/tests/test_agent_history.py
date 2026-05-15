"""Unit-тесты ``/api/agents/{name}/history`` endpoint."""

from __future__ import annotations

import pathlib
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from core.dashboard.api import create_app
from core.dashboard.state import _extract_confidence
from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import DecisionContext


def _seed(db: pathlib.Path) -> None:
    log = TradeOutcomeLogger(db)
    for i, conf in enumerate([0.5, 0.7, 0.62, 0.81]):
        log.record_entry(
            DecisionContext(
                trade_id=f"t{i}",
                symbol="BTC-USDT",
                side="BUY",
                entry_time_ms=1_700_000_000_000 + i * 60_000,
                entry_price=Decimal("80500"),
                size=Decimal("0.1"),
                signal_candidate={"action": "BUY"},
                market_analyst={"state": "TRENDING_UP", "confidence": conf + 0.1},
                sentiment_analyst={"sentiment_score": 0.3, "confidence": 0.8},
                risk_overseer={"approved": True, "confidence": 0.9},
                macro_analyst={"regime": "RISK_ON", "confidence": 0.6},
                coordinator={"action": "BUY", "composite_confidence": conf},
            )
        )


@pytest.fixture
def client(tmp_path: pathlib.Path) -> TestClient:
    db = tmp_path / "outcomes.sqlite"
    _seed(db)
    app = create_app(outcomes_db=db, halt_flag_file=None, heartbeat_file=None)
    return TestClient(app)


def test_coordinator_history(client: TestClient) -> None:
    data = client.get("/api/agents/coordinator/history").json()
    assert data["agent"] == "coordinator"
    assert len(data["points"]) == 4
    # DESC by time — последняя сделка первой
    first = data["points"][0]
    assert first["value"] == 0.81


def test_sentiment_history_normalizes_score(client: TestClient) -> None:
    """sentiment_score [-1,1] → [0,1] для sparkline."""
    data = client.get("/api/agents/sentiment_analyst/history").json()
    # 0.3 → (0.3+1)/2 = 0.65
    assert data["points"][0]["value"] == pytest.approx(0.65)


def test_unknown_agent_404(client: TestClient) -> None:
    assert client.get("/api/agents/coordinator_2/history").status_code == 404


def test_invalid_limit(client: TestClient) -> None:
    assert client.get("/api/agents/coordinator/history?limit=0").status_code == 400
    assert client.get("/api/agents/coordinator/history?limit=200").status_code == 400


def test_extract_confidence_clamps() -> None:
    """Значения вне [0, 1] обрезаются."""
    assert _extract_confidence({"confidence": 1.5}, "market_analyst") == 1.0
    assert _extract_confidence({"confidence": -0.5}, "market_analyst") == 0.0
    assert _extract_confidence({"composite_confidence": 0.7}, "coordinator") == 0.7


def test_extract_confidence_returns_none_for_missing() -> None:
    assert _extract_confidence({}, "coordinator") is None
    assert _extract_confidence({"other_field": 0.5}, "coordinator") is None


def test_history_limit(client: TestClient) -> None:
    data = client.get("/api/agents/coordinator/history?limit=2").json()
    assert len(data["points"]) == 2
