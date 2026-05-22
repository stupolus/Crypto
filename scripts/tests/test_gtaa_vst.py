"""Тесты чистых функций gtaa_vst_executor (без сети)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from core.risk import RiskEngine
from scripts import gtaa_vst_executor
from scripts.gtaa_vst_executor import (
    _ASSETS,
    AssetPlan,
    format_rebalance_summary,
    is_halted,
    latest_eom_with_sma,
    plan_asset_action,
    should_rebalance,
)
from scripts.gtaa_vst_report import build_report

_ENGINE = RiskEngine()
_MMR = Decimal(str(_ENGINE.config.limits.maintenance_margin_rate))
_ZERO_PNL = (Decimal("0"), Decimal("0"), Decimal("0"))


def _plan(
    idx_close: float,
    sma200: float,
    perp_price: str,
    cur_qty: str,
    equity_share: str = "25000",
) -> AssetPlan:
    """Хелпер: план по 1 активу с дефолтными «здоровыми» брейкерами."""
    return plan_asset_action(
        _ASSETS[0],
        idx_close,
        sma200,
        Decimal(perp_price),
        Decimal(cur_qty),
        Decimal(equity_share),
        _ENGINE,
        _MMR,
        _ZERO_PNL,
        day_trades=0,
        consecutive_losses=0,
    )


def _make_daily(n: int, start: date = date(2026, 1, 1)) -> list[tuple[date, float]]:
    """Линейные daily-данные для теста SMA200."""
    return [(date.fromordinal(start.toordinal() + i), 100.0 + i * 0.1) for i in range(n)]


def test_should_rebalance_first_run() -> None:
    """state без last_rebalance_eom → ребалансируем."""
    assert should_rebalance(date(2026, 5, 30), None) is True


def test_should_rebalance_already_done() -> None:
    """Тот же EOM → noop."""
    assert should_rebalance(date(2026, 5, 30), "2026-05-30") is False


def test_should_rebalance_new_month() -> None:
    """Новая EOM-дата → ребалансируем."""
    assert should_rebalance(date(2026, 6, 30), "2026-05-30") is True


def test_should_rebalance_old_eom_skipped() -> None:
    """Старая EOM (state опередил) → noop (защита от гонок)."""
    assert should_rebalance(date(2026, 4, 30), "2026-05-30") is False


def test_latest_eom_too_short_returns_none() -> None:
    """Меньше SMA_N+1 точек → None."""
    rows = _make_daily(50)  # SMA_N=200, не хватит
    assert latest_eom_with_sma(rows) is None


def test_latest_eom_picks_last_day_of_last_month() -> None:
    """EOM = последний наблюдаемый день последнего месяца в данных."""
    rows = _make_daily(250)  # 250 дней с 2026-01-01
    res = latest_eom_with_sma(rows)
    assert res is not None
    d_eom, c_eom, sma = res
    # Последний день в данных
    assert d_eom == rows[-1][0]
    # close = последнее значение
    assert c_eom == rows[-1][1]
    # SMA200 = среднее последних 200 значений
    expected_sma = sum(c for (_d, c) in rows[-200:]) / 200
    assert abs(sma - expected_sma) < 1e-9


def test_latest_eom_returns_last_per_bucket() -> None:
    """Внутри последнего (year, month) — берём последнюю дату месяца."""
    # 220 дней + дополнительные дни в новом месяце
    rows = _make_daily(220)
    # Добавим ещё 3 дня нового месяца
    rows.extend(
        [(date(2026, 8, 11), 200.0), (date(2026, 8, 12), 201.0), (date(2026, 8, 13), 202.0)]
    )
    res = latest_eom_with_sma(rows)
    assert res is not None
    d_eom, _c, _sma = res
    # Последний день последнего месяца в данных
    assert d_eom == date(2026, 8, 13)


def test_kill_switch(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    halt = tmp_path / "gtaa_HALT"
    monkeypatch.setattr(gtaa_vst_executor, "_HALT", halt)
    assert is_halted() is False
    halt.write_text("stop")
    assert is_halted() is True


def test_http_get_json_retries_then_succeeds(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """2 сбоя сети → 3-я попытка успешна. Без реальных пауз."""
    calls = {"n": 0}

    class _FakeResp:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *a: object) -> None:
            return None

    def _fake_urlopen(req: object, timeout: float = 0) -> _FakeResp:
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("network down")
        return _FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    monkeypatch.setattr("json.load", lambda fh: {"ok": True})
    monkeypatch.setattr("time.sleep", lambda _s: None)

    assert gtaa_vst_executor._http_get_json("http://x") == {"ok": True}
    assert calls["n"] == 3


def test_http_get_json_gives_up(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Все попытки провалены → пробрасывает последнее исключение."""

    def _always_fail(req: object, timeout: float = 0) -> object:
        raise OSError("boom")

    monkeypatch.setattr("urllib.request.urlopen", _always_fail)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    with pytest.raises(OSError, match="boom"):
        gtaa_vst_executor._http_get_json("http://x", retries=3)


def test_format_rebalance_summary() -> None:
    rows: list[dict[str, object]] = [
        {"label": "GSPC", "signal": "LONG", "action": "open_long", "status": "ok"},
        {"label": "GC", "signal": "CASH", "action": "noop", "status": "ok"},
        {"label": "CL", "signal": "LONG", "action": "rebalance", "status": "error"},
    ]
    s = format_rebalance_summary(date(2026, 5, 29), rows)
    assert "EOM=2026-05-29" in s
    assert "2/3 ok" in s
    assert "GSPC:LONG→open_long[ok]" in s
    assert "CL:LONG→rebalance[error]" in s


def test_build_report_healthy() -> None:
    txt = build_report(
        now=datetime(2026, 5, 22, 21, 45, tzinfo=UTC),
        fired_24h=1,
        last_eom="2026-04-30",
        halted=False,
        errors_24h=[],
        positions={"GSPC": Decimal("0.5"), "GC": Decimal("0")},
        equity=Decimal("100000"),
    )
    assert "timer: OK" in txt
    assert "GSPC=ON 0.5" in txt
    assert "GC=cash" in txt
    assert "ошибок/24ч: 0" in txt
    assert "HALT" not in txt


def test_build_report_flags_no_heartbeat_and_errors() -> None:
    txt = build_report(
        now=datetime(2026, 5, 22, 21, 45, tzinfo=UTC),
        fired_24h=0,
        last_eom=None,
        halted=True,
        errors_24h=[{"label": "NDX", "err": "Timeout"}],
        positions={},
        equity=None,
    )
    assert "НЕТ СРАБАТЫВАНИЙ" in txt
    assert "HALT активен" in txt
    assert "ошибок/24ч: 1" in txt
    assert "NDX: Timeout" in txt
    assert "позиции не получены" in txt


# --- plan_asset_action: ядро исполнения (DEMO_CRITERIA 3/4/5) ---


def test_plan_on_flat_opens_long() -> None:
    """ON (close>SMA200) + нет позиции → open_long, target>0."""
    p = _plan(idx_close=110.0, sma200=100.0, perp_price="100", cur_qty="0")
    assert p.signal == "LONG"
    assert p.action == "open_long"
    assert p.target_qty > 0
    assert p.stop_px < p.perp_price  # стоп ниже входа (LONG)
    assert p.liq_est is not None and p.liq_est < p.perp_price


def test_plan_off_flat_noop() -> None:
    """OFF (close<SMA200) + нет позиции → noop, target=0."""
    p = _plan(idx_close=90.0, sma200=100.0, perp_price="100", cur_qty="0")
    assert p.signal == "CASH"
    assert p.action == "noop"
    assert p.target_qty == 0


def test_plan_off_with_position_closes() -> None:
    """OFF + есть LONG-позиция → close (выход в кэш)."""
    p = _plan(idx_close=90.0, sma200=100.0, perp_price="100", cur_qty="5")
    assert p.signal == "CASH"
    assert p.action == "close"
    assert p.target_qty == 0


def test_plan_on_already_in_target_noop() -> None:
    """ON + позиция уже ≈target (в пределах толеранса) → noop (нет дублей)."""
    p0 = _plan(idx_close=110.0, sma200=100.0, perp_price="100", cur_qty="0")
    # повтор с фактической позицией = target → idempotent noop
    p1 = _plan(idx_close=110.0, sma200=100.0, perp_price="100", cur_qty=str(p0.target_qty))
    assert p1.action == "noop"


def test_plan_quarter_budget_leverage_capped() -> None:
    """target_qty не превышает 3x на доле 1/4 эквити (нотионал ≤ 3·share)."""
    share = Decimal("25000")
    p = _plan(
        idx_close=110.0,
        sma200=100.0,
        perp_price="100",
        cur_qty="0",
        equity_share=str(share),
    )
    notional = p.target_qty * p.perp_price
    assert notional <= share * Decimal("3") + Decimal("1")  # +1 округление


def test_plan_equal_share_across_assets() -> None:
    """Два ON-актива с одной долей 1/4 → одинаковый нотионал (доли ¼)."""
    share = Decimal("25000")
    a = _plan(idx_close=110.0, sma200=100.0, perp_price="100",
              cur_qty="0", equity_share=str(share))  # fmt: skip
    b = _plan(idx_close=220.0, sma200=200.0, perp_price="200",
              cur_qty="0", equity_share=str(share))  # fmt: skip
    # нотионал = qty*price; при равной доле и равном risk% должен совпадать
    assert abs(a.target_qty * a.perp_price - b.target_qty * b.perp_price) <= Decimal("200")
