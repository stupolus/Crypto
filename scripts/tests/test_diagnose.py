"""Unit-тесты ``scripts.diagnose`` — изолированные проверки helper'ов."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import DecisionContext, ExitData
from scripts.diagnose import (
    _check_anthropic,
    _check_bingx,
    _check_dependencies,
    _check_env_file,
    _check_env_var,
    _check_outcomes_db,
    run_diagnostics,
)


def test_check_env_file_present() -> None:
    """Проверяем что .env файл найден (если есть в репо)."""
    ok, msg = _check_env_file()
    # В CI .env может отсутствовать — оба исхода валидные, проверяем формат.
    assert "✓" in msg or "✗" in msg


def test_check_env_var_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NONEXISTENT_VAR_XYZ", raising=False)
    ok, msg = _check_env_var("NONEXISTENT_VAR_XYZ", required=False)
    assert ok is False
    assert "НЕ задан" in msg


def test_check_env_var_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TEST_VAR_ABC", "secretvalue1234")
    ok, msg = _check_env_var("MY_TEST_VAR_ABC", required=False)
    assert ok is True
    assert "1234" in msg  # last 4 chars


def test_check_dependencies_lists_results() -> None:
    ok, lines = _check_dependencies()
    # Все эти модули должны быть установлены в проекте
    assert ok is True
    assert any("httpx" in line for line in lines)
    assert any("pydantic" in line for line in lines)


def test_check_outcomes_db_missing(tmp_path: Path) -> None:
    ok, lines = _check_outcomes_db(tmp_path / "missing.sqlite")
    assert ok is True  # Missing == warning, not failure
    assert any("не существует" in line for line in lines)


def test_check_outcomes_db_empty(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite"
    TradeOutcomeLogger(db)
    ok, lines = _check_outcomes_db(db)
    assert ok is True
    assert any("0 записей" in line for line in lines)


def test_check_outcomes_db_with_data(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite"
    log = TradeOutcomeLogger(db)
    # 1 win + 1 loss
    for tid, loss in [("w1", False), ("l1", True)]:
        ctx = DecisionContext(
            trade_id=tid,
            symbol="BTC-USDT",
            side="BUY",
            entry_time_ms=1_700_000_000_000,
            entry_price=Decimal("80500"),
            size=Decimal("0.1"),
            signal_candidate={},
            market_analyst={},
            sentiment_analyst={},
            risk_overseer={},
            macro_analyst={},
            coordinator={},
        )
        log.record_entry(ctx)
        log.record_exit(
            tid,
            ExitData(
                exit_time_ms=1_700_000_900_000,
                exit_price=Decimal("79000") if loss else Decimal("82000"),
                pnl_usd=Decimal("-50") if loss else Decimal("100"),
                pnl_pct=Decimal("-1.5") if loss else Decimal("2.0"),
                exit_reason="SL" if loss else "TP1",
                holding_time_min=15,
            ),
        )

    ok, lines = _check_outcomes_db(db)
    assert ok is True
    text = "\n".join(lines)
    assert "2 записей" in text
    assert "wins=1" in text
    assert "losses=1" in text


def test_check_anthropic_when_configured() -> None:
    """Если .env есть в репо с реальным ключом — тест работает."""
    ok, msg = _check_anthropic()
    # Просто проверяем формат — флаг зависит от env
    assert "ANTHROPIC" in msg


def test_check_bingx_returns_status() -> None:
    ok, msg = _check_bingx()
    # Зависит от .env; проверяем что вернулся валидный ответ
    assert "BingX" in msg or "BINGX" in msg


def test_run_diagnostics_returns_exit_code(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Smoke test: запускается без exception."""
    rc = run_diagnostics(outcomes_db=tmp_path / "no.sqlite")
    assert rc in (0, 1)
    out = capsys.readouterr().out
    assert "Diagnostic Report" in out
    assert "Critical credentials" in out
