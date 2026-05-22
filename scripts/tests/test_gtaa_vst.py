"""Тесты чистых функций gtaa_vst_executor (без сети)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from core.risk import RiskEngine
from scripts import gtaa_vst_executor
from scripts.gtaa_vst_executor import (
    _ASSETS,
    AssetPlan,
    format_preflight,
    format_rebalance_summary,
    is_halted,
    latest_eom_with_sma,
    plan_asset_action,
    should_rebalance,
)
from scripts.gtaa_vst_report import build_report
from scripts.gtaa_vst_verdict import build_verdict

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


# --- format_preflight (read-only проверка перед запуском) ---


def test_format_preflight_ready() -> None:
    """Все 4 актива + BingX OK + env=vst → ГОТОВ К ЗАПУСКУ."""
    rows = [(a.label, "2026-04-30", 110.0, 100.0, "LONG") for a in _ASSETS]
    txt = format_preflight("vst", rows, True, Decimal("100000"), [])
    assert "ГОТОВ К ЗАПУСКУ" in txt
    assert "sma200=100.00 → LONG" in txt
    assert "BingX VST: OK" in txt


def test_format_preflight_flags_problems() -> None:
    """env!=vst или ошибки/неполные данные → ЕСТЬ ПРОБЛЕМЫ."""
    txt = format_preflight("live", [], False, None, ["GSPC: yahoo Timeout"])
    assert "ЕСТЬ ПРОБЛЕМЫ" in txt
    assert "ОЖИДАЛОСЬ vst" in txt
    assert "НЕТ СВЯЗИ" in txt
    assert "GSPC: yahoo Timeout" in txt


def test_format_preflight_incomplete_not_ready() -> None:
    """env=vst, BingX OK, но не все 4 актива → НЕ готов."""
    rows = [("GSPC", "2026-04-30", 110.0, 100.0, "LONG")]
    txt = format_preflight("vst", rows, True, Decimal("100000"), [])
    assert "ЕСТЬ ПРОБЛЕМЫ" in txt


# --- build_verdict (ШАГ 4: факты из логов, не PnL) ---


def _ts(day: int) -> int:
    """ts для дня 2026-05-<day> 21:30 UTC."""
    return int(datetime(2026, 5, day, 21, 30, tzinfo=UTC).timestamp())


def test_verdict_reliable_when_all_days_fired_and_rebalance_caught() -> None:
    rows: list[dict[str, object]] = []
    for d in range(1, 29):  # 28 дней подряд — heartbeat каждый день
        rows.append({"ts": _ts(d), "action": "fired"})
    # один день — реальный ребаланс (open_long ok)
    rows.append({"ts": _ts(28), "action": "open_long", "status": "ok", "label": "GSPC"})
    txt = build_verdict(
        datetime(2026, 5, 29, tzinfo=UTC), rows, {"last_rebalance_eom": "2026-04-30"}
    )
    assert "ИСПОЛНЕНИЕ: НАДЁЖНО" in txt
    assert "28/28" in txt
    assert "Ребалансов исполнено (ok): 1" in txt
    assert "PnL: НЕ оценивается" in txt


def test_verdict_flags_gaps_and_errors() -> None:
    rows: list[dict[str, object]] = [
        {"ts": _ts(1), "action": "fired"},
        {"ts": _ts(5), "action": "fired"},  # пропуск дней 2-4
        {
            "ts": _ts(5),
            "action": "rebalance",
            "status": "error",
            "label": "CL",
            "err": "BingXError: position side",
        },
    ]
    txt = build_verdict(datetime(2026, 5, 6, tzinfo=UTC), rows, {})
    assert "НЕ ПОДТВЕРЖДЕНО" in txt
    assert "ПРОПУСКИ" in txt
    assert "Ошибок исполнения: 1" in txt
    assert "CL: BingXError: position side" in txt


def test_verdict_incomplete_when_no_rebalance() -> None:
    rows: list[dict[str, object]] = [{"ts": _ts(d), "action": "fired"} for d in range(1, 29)]
    txt = build_verdict(datetime(2026, 5, 29, tzinfo=UTC), rows, {})
    assert "НЕ ПОДТВЕРЖДЕНО" in txt
    assert "ни одного ребаланса" in txt


def test_verdict_no_data() -> None:
    txt = build_verdict(datetime(2026, 5, 29, tzinfo=UTC), [], {})
    assert "нет данных" in txt
    assert "НЕ ПОДТВЕРЖДЕНО" in txt


# --- _rebalance: оффлайн интеграция с фейковым BingX API ---


class _FakeBalance:
    def __init__(self, asset: str, equity: str) -> None:
        self.asset = asset
        self.equity = equity


class _FakePos:
    def __init__(self, amt: str) -> None:
        self.position_amount = amt


class _FakeAck:
    order_id = "FAKE-1"


class _FakeAPI:
    def __init__(self, *, fail_positions: bool = False) -> None:
        self._fail = fail_positions
        self.orders: list[object] = []
        self.closed: list[str] = []

    async def get_balance(self) -> list[_FakeBalance]:
        return [_FakeBalance("VST", "100000")]

    async def get_positions(self, symbol: str) -> list[_FakePos]:
        if self._fail:
            raise RuntimeError("BingX API error 100410: rate limit disabled period")
        return []  # нет открытых позиций

    async def close_position(self, symbol: str) -> None:
        self.closed.append(symbol)

    async def place_order(self, req: object) -> _FakeAck:
        self.orders.append(req)
        return _FakeAck()


class _FakeClient:
    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *a: object) -> None:
        return None


def _all_long_eoms() -> dict[str, tuple[date, float, float]]:
    return {a.label: (date(2026, 4, 30), 110.0, 100.0) for a in _ASSETS}


def _perp_pxs() -> dict[str, float]:
    return {a.label: 100.0 for a in _ASSETS}


def _patch_bingx(monkeypatch, api: _FakeAPI, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(gtaa_vst_executor, "BingXClient", lambda settings: _FakeClient())
    monkeypatch.setattr(gtaa_vst_executor, "PrivateAPI", lambda c: api)
    monkeypatch.setattr(gtaa_vst_executor, "_STATE", tmp_path / "state.json")
    monkeypatch.setattr(gtaa_vst_executor, "_LOG", tmp_path / "log.jsonl")


def _run_rebalance(api: _FakeAPI, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import asyncio
    from types import SimpleNamespace
    from typing import cast

    from adapters.bingx.settings import BingXSettings
    from core.alerts import NoopAlerter

    _patch_bingx(monkeypatch, api, tmp_path)
    s = cast(BingXSettings, SimpleNamespace(env="vst"))
    asyncio.run(
        gtaa_vst_executor._rebalance(
            s, False, _all_long_eoms(), _perp_pxs(), {}, date(2026, 4, 30), NoopAlerter()
        )
    )


def test_rebalance_happy_path_opens_four_and_writes_state(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Все 4 ON, нет позиций → 4 ордера + state.last_rebalance_eom записан."""
    api = _FakeAPI()
    _run_rebalance(api, tmp_path, monkeypatch)
    assert len(api.orders) == len(_ASSETS)  # 4 open_long
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["last_rebalance_eom"] == "2026-04-30"


def test_rebalance_read_error_aborts_without_state(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """get_positions падает → НЕ крашится, ордеров нет, state не записан."""
    api = _FakeAPI(fail_positions=True)
    _run_rebalance(api, tmp_path, monkeypatch)
    assert api.orders == []  # ни одного ордера
    assert not (tmp_path / "state.json").exists()  # state не тронут → ретрай
    log = (tmp_path / "log.jsonl").read_text()
    assert "read_error" in log
