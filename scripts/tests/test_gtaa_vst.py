"""Тесты чистых функций gtaa_vst_executor (без сети)."""

from __future__ import annotations

from datetime import date

from scripts import gtaa_vst_executor
from scripts.gtaa_vst_executor import (
    is_halted,
    latest_eom_with_sma,
    should_rebalance,
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
