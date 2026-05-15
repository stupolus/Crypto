"""Unit-тесты FastAPI dashboard."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.dashboard.api import create_app
from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import DecisionContext, ExitData


def _seed_db(db_path: Path, *, with_closed: bool = True, with_open: bool = True) -> None:
    log = TradeOutcomeLogger(db_path)

    def _ctx(trade_id: str) -> DecisionContext:
        return DecisionContext(
            trade_id=trade_id,
            symbol="BTC-USDT",
            side="BUY",
            entry_time_ms=1_700_000_000_000,
            entry_price=Decimal("80500"),
            size=Decimal("0.1"),
            signal_candidate={"action": "BUY"},
            market_analyst={"state": "TRENDING_UP", "volatility": "normal"},
            sentiment_analyst={"sentiment_score": 0.4},
            risk_overseer={"approved": True, "max_risk_pct": 1.0},
            macro_analyst={"regime": "RISK_ON"},
            coordinator={"action": "BUY", "composite_confidence": 0.72},
            latency_decision_ms=420,
        )

    if with_closed:
        log.record_entry(_ctx("win_1"))
        log.record_exit(
            "win_1",
            ExitData(
                exit_time_ms=1_700_000_900_000,
                exit_price=Decimal("82000"),
                pnl_usd=Decimal("150"),
                pnl_pct=Decimal("1.86"),
                exit_reason="TP1",
                holding_time_min=15,
            ),
        )
        log.record_entry(_ctx("loss_1"))
        log.record_exit(
            "loss_1",
            ExitData(
                exit_time_ms=1_700_000_900_001,
                exit_price=Decimal("79800"),
                pnl_usd=Decimal("-70"),
                pnl_pct=Decimal("-0.87"),
                exit_reason="SL",
                holding_time_min=15,
            ),
        )
    if with_open:
        log.record_entry(_ctx("open_1"))


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    db = tmp_path / "outcomes.sqlite"
    _seed_db(db)
    halt = tmp_path / "halt"  # отсутствует → no halt
    hb = tmp_path / "hb"
    hb.touch()
    app = create_app(outcomes_db=db, halt_flag_file=halt, heartbeat_file=hb)
    return TestClient(app)


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["halt_active"] is False


def test_health_halted(tmp_path: Path) -> None:
    db = tmp_path / "outcomes.sqlite"
    _seed_db(db, with_closed=False, with_open=False)
    halt = tmp_path / "halt"
    halt.write_text(
        "HALTED\ncreated_at: 2026-05-14T22:00:00+00:00\nsource: manual\nnote: test halt\n",
        encoding="utf-8",
    )
    app = create_app(outcomes_db=db, halt_flag_file=halt, heartbeat_file=None)
    c = TestClient(app)
    data = c.get("/api/health").json()
    assert data["status"] == "halted"
    assert data["halt_active"] is True
    assert data["halt_reason"]["source"] == "manual"


def test_status(client: TestClient) -> None:
    data = client.get("/api/status").json()
    assert data["trades"]["total"] == 3  # 2 closed + 1 open
    assert data["trades"]["open"] == 1
    assert data["trades"]["closed"] == 2
    assert data["trades"]["wins"] == 1
    assert data["trades"]["losses"] == 1
    assert data["trades"]["win_rate_pct"] == 50.0
    assert len(data["open_trades"]) == 1
    assert data["open_trades"][0]["trade_id"] == "open_1"


def test_agents(client: TestClient) -> None:
    data = client.get("/api/agents").json()
    agents = {a["name"]: a for a in data["agents"]}
    assert set(agents) == {
        "market_analyst",
        "sentiment_analyst",
        "risk_overseer",
        "macro_analyst",
        "coordinator",
    }
    assert agents["market_analyst"]["last_payload"]["state"] == "TRENDING_UP"
    assert agents["coordinator"]["last_payload"]["action"] == "BUY"


def test_trades_default(client: TestClient) -> None:
    data = client.get("/api/trades").json()
    assert len(data["trades"]) == 3


def test_trades_only_open(client: TestClient) -> None:
    data = client.get("/api/trades?only_open=true").json()
    assert len(data["trades"]) == 1
    assert data["trades"][0]["trade_id"] == "open_1"


def test_trades_only_closed(client: TestClient) -> None:
    data = client.get("/api/trades?only_closed=true").json()
    assert len(data["trades"]) == 2
    assert all(t["is_closed"] for t in data["trades"])


def test_trades_limit(client: TestClient) -> None:
    data = client.get("/api/trades?limit=1").json()
    assert len(data["trades"]) == 1


def test_trades_limit_out_of_range(client: TestClient) -> None:
    assert client.get("/api/trades?limit=0").status_code == 400
    assert client.get("/api/trades?limit=600").status_code == 400


def test_trade_detail_found(client: TestClient) -> None:
    data = client.get("/api/trades/win_1").json()
    assert data["trade_id"] == "win_1"
    assert data["exit_reason"] == "TP1"
    assert data["is_win"] is True
    # LLM payloads parsed как dict, не raw JSON string
    assert data["market_analyst"]["state"] == "TRENDING_UP"
    assert data["coordinator"]["composite_confidence"] == 0.72


def test_trade_detail_not_found(client: TestClient) -> None:
    resp = client.get("/api/trades/nonexistent")
    assert resp.status_code == 404


def test_equity_curve(client: TestClient) -> None:
    data = client.get("/api/equity").json()
    # 2 closed trades → 2 точки
    assert len(data["points"]) == 2
    # Cumulative должно расти/падать монотонно
    pnls = [p["pnl_usd"] for p in data["points"]]
    assert "150" in pnls or "-70" in pnls


def test_equity_limit_validation(client: TestClient) -> None:
    assert client.get("/api/equity?limit=0").status_code == 400
    assert client.get("/api/equity?limit=2000").status_code == 400


def test_empty_db(tmp_path: Path) -> None:
    """С пустым outcomes journal все endpoints работают без ошибок."""
    db = tmp_path / "empty.sqlite"
    app = create_app(outcomes_db=db, halt_flag_file=None, heartbeat_file=None)
    c = TestClient(app)
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/status").json()["trades"]["total"] == 0
    assert c.get("/api/trades").json()["trades"] == []
    assert c.get("/api/equity").json()["points"] == []
    # Agents возвращают 5 пустых snapshot'ов
    agents = c.get("/api/agents").json()["agents"]
    assert len(agents) == 5
    assert all(a["last_payload"] == {} for a in agents)


def test_symbol_filter_and_endpoint(tmp_path: Path) -> None:
    """/api/trades?symbol=X фильтрует по symbol; /api/symbols возвращает список."""
    from core.postmortem.models import DecisionContext, ExitData

    db = tmp_path / "outcomes.sqlite"
    log = TradeOutcomeLogger(db)

    def _ctx(trade_id: str, sym: str) -> DecisionContext:
        return DecisionContext(
            trade_id=trade_id,
            symbol=sym,
            side="BUY",
            entry_time_ms=1_700_000_000_000,
            entry_price=Decimal("80500"),
            size=Decimal("0.1"),
            signal_candidate={"action": "BUY"},
            market_analyst={},
            sentiment_analyst={},
            risk_overseer={},
            macro_analyst={},
            coordinator={},
            latency_decision_ms=420,
        )

    log.record_entry(_ctx("b1", "BTC-USDT"))
    log.record_entry(_ctx("x1", "XAUT-USDT"))
    log.record_entry(_ctx("x2", "XAUT-USDT"))
    log.record_exit(
        "x1",
        ExitData(
            exit_time_ms=1_700_000_900_000,
            exit_price=Decimal("82000"),
            pnl_usd=Decimal("100"),
            pnl_pct=Decimal("1.2"),
            exit_reason="TP1",
            holding_time_min=10,
        ),
    )

    app = create_app(outcomes_db=db, halt_flag_file=None, heartbeat_file=None)
    c = TestClient(app)

    # /api/symbols возвращает unique sorted
    symbols = c.get("/api/symbols").json()["symbols"]
    assert symbols == ["BTC-USDT", "XAUT-USDT"]

    # /api/trades без фильтра → все 3
    assert len(c.get("/api/trades").json()["trades"]) == 3

    # /api/trades?symbol=XAUT-USDT → только 2
    only_xaut = c.get("/api/trades?symbol=XAUT-USDT").json()["trades"]
    assert len(only_xaut) == 2
    assert all(t["symbol"] == "XAUT-USDT" for t in only_xaut)


def test_strategy_stats_groups_by_symbol(tmp_path: Path) -> None:
    """/api/strategy_stats группирует outcomes по SYMBOL_TO_STRATEGY mapping."""
    from core.postmortem.models import DecisionContext, ExitData

    db = tmp_path / "outcomes.sqlite"
    log = TradeOutcomeLogger(db)

    def _ctx(trade_id: str, sym: str) -> DecisionContext:
        return DecisionContext(
            trade_id=trade_id,
            symbol=sym,
            side="BUY",
            entry_time_ms=1_700_000_000_000,
            entry_price=Decimal("80500"),
            size=Decimal("0.1"),
            signal_candidate={"action": "BUY"},
            market_analyst={},
            sentiment_analyst={},
            risk_overseer={},
            macro_analyst={},
            coordinator={},
            latency_decision_ms=420,
        )

    # 2 BTC trades (1 win, 1 loss), 1 XAUT win, 1 XAUT open
    log.record_entry(_ctx("b1", "BTC-USDT"))
    log.record_exit(
        "b1",
        ExitData(
            exit_time_ms=1_700_000_900_000,
            exit_price=Decimal("82000"),
            pnl_usd=Decimal("150"),
            pnl_pct=Decimal("1.86"),
            exit_reason="TP1",
            holding_time_min=10,
        ),
    )
    log.record_entry(_ctx("b2", "BTC-USDT"))
    log.record_exit(
        "b2",
        ExitData(
            exit_time_ms=1_700_000_900_001,
            exit_price=Decimal("79000"),
            pnl_usd=Decimal("-100"),
            pnl_pct=Decimal("-1.2"),
            exit_reason="SL",
            holding_time_min=10,
        ),
    )
    log.record_entry(_ctx("x1", "XAUT-USDT"))
    log.record_exit(
        "x1",
        ExitData(
            exit_time_ms=1_700_000_900_002,
            exit_price=Decimal("2150"),
            pnl_usd=Decimal("50"),
            pnl_pct=Decimal("2.4"),
            exit_reason="TP1",
            holding_time_min=120,
        ),
    )
    log.record_entry(_ctx("x2", "XAUT-USDT"))  # still open

    app = create_app(outcomes_db=db, halt_flag_file=None, heartbeat_file=None)
    c = TestClient(app)
    data = c.get("/api/strategy_stats").json()
    by_strat = {s["strategy"]: s for s in data["strategies"]}

    # btc_breakout: 2 closed, 1 win, 1 loss, 50% wr, PF = 150/100 = 1.50
    assert by_strat["btc_breakout"]["total"] == 2
    assert by_strat["btc_breakout"]["wins"] == 1
    assert by_strat["btc_breakout"]["losses"] == 1
    assert by_strat["btc_breakout"]["win_rate_pct"] == 50.0
    assert by_strat["btc_breakout"]["profit_factor"] == "1.50"
    assert by_strat["btc_breakout"]["total_pnl_usd"] == "50"

    # gold_safety_haven: 1 closed win + 1 open
    assert by_strat["gold_safety_haven"]["total"] == 2
    assert by_strat["gold_safety_haven"]["closed"] == 1
    assert by_strat["gold_safety_haven"]["open"] == 1
    assert by_strat["gold_safety_haven"]["wins"] == 1
    assert by_strat["gold_safety_haven"]["win_rate_pct"] == 100.0
    assert by_strat["gold_safety_haven"]["profit_factor"] == "inf"  # no losses
    assert by_strat["gold_safety_haven"]["total_pnl_usd"] == "50"


def test_multi_db_merge(tmp_path: Path) -> None:
    """Multi-runner setup: outcomes_db = список DB → дашборд сливает все.

    Каждый runner пишет в свою sqlite (llm-BTC-outcomes.sqlite,
    llm-XAU-outcomes.sqlite, ...). Дашборд агрегирует.
    """
    db_btc = tmp_path / "llm-BTC-outcomes.sqlite"
    db_xau = tmp_path / "llm-XAU-outcomes.sqlite"
    _seed_db(db_btc, with_open=False)  # 2 closed (win + loss) в BTC
    _seed_db(db_xau, with_closed=False)  # 1 open в XAU

    app = create_app(
        outcomes_db=[db_btc, db_xau],
        halt_flag_file=None,
        heartbeat_file=None,
    )
    c = TestClient(app)
    status = c.get("/api/status").json()
    # 2 closed + 1 open = 3 total
    assert status["trades"]["total"] == 3
    assert status["trades"]["closed"] == 2
    assert status["trades"]["open"] == 1

    # trade_detail умеет найти trade в любой из DB.
    btc_win = c.get("/api/trades/win_1").json()
    assert btc_win["trade_id"] == "win_1"
    xau_open = c.get("/api/trades/open_1").json()
    assert xau_open["trade_id"] == "open_1"
