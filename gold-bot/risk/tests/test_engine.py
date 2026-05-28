"""Тесты RiskEngine: sizing, ликвидационный буфер, все circuit breakers."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from exchanges.models import OrderSide
from risk.config import load_risk_config
from risk.engine import EntryContext, RiskEngine, RiskState, compute_sizing

CFG = load_risk_config()


def _ctx(**overrides: object) -> EntryContext:
    base: dict[str, object] = {
        "symbol": "BTC/USDT:USDT",
        "asset_class": "crypto",
        "side": OrderSide.BUY,
        "equity": Decimal("10000"),
        "entry": Decimal("100"),
        "stop": Decimal("99"),
        "risk_pct": Decimal("0.005"),
        "expected_tp_pct": Decimal("0.02"),
        "expected_cost_pct": Decimal("0.005"),
        "spread": Decimal("1"),
        "spread_median": Decimal("1"),
        "now_ts": 1_000_000.0,
    }
    base.update(overrides)
    return EntryContext(**base)  # type: ignore[arg-type]


def _state() -> RiskState:
    return RiskState.new(Decimal("10000"), date(2026, 5, 20))


# ── config ──
def test_config_mirrors_risk_profile_key_numbers() -> None:
    assert CFG.max_effective_leverage == Decimal("5")
    assert CFG.daily_stop_pct == Decimal("-0.02")
    assert CFG.global_killswitch_dd_pct == Decimal("-0.15")
    assert CFG.max_positions_total == 3


# ── compute_sizing ──
def test_sizing_happy_path() -> None:
    d = compute_sizing(
        CFG, Decimal("10000"), Decimal("100"), Decimal("99"), OrderSide.BUY, Decimal("0.005")
    )
    assert d.approved
    assert d.sizing is not None
    assert d.sizing.risk_amount == Decimal("50")
    assert d.sizing.notional == Decimal("5000")
    assert d.sizing.effective_leverage == Decimal("0.5")


def test_sizing_rejects_tight_stop() -> None:
    d = compute_sizing(
        CFG, Decimal("10000"), Decimal("100"), Decimal("99.9"), OrderSide.BUY, Decimal("0.005")
    )
    assert not d.approved
    assert d.reason == "stop_too_tight"


def test_sizing_rejects_wrong_side() -> None:
    d = compute_sizing(
        CFG, Decimal("10000"), Decimal("100"), Decimal("101"), OrderSide.BUY, Decimal("0.005")
    )
    assert d.reason == "stop_wrong_side"


def test_sizing_rejects_leverage() -> None:
    # risk_pct выше потолка при узком стопе → eff_lev > 5
    d = compute_sizing(
        CFG, Decimal("10000"), Decimal("100"), Decimal("99.7"), OrderSide.BUY, Decimal("0.02")
    )
    assert d.reason == "leverage_exceeded"


def test_sizing_rejects_liquidation_buffer_on_wide_stop() -> None:
    # стоп шире буфера ликвидации (стоп оказывается за ценой ликвидации)
    d = compute_sizing(
        CFG, Decimal("10000"), Decimal("100"), Decimal("80"), OrderSide.BUY, Decimal("0.005")
    )
    assert d.reason == "liquidation_buffer"


def test_sizing_invalid_inputs() -> None:
    d = compute_sizing(
        CFG, Decimal("0"), Decimal("100"), Decimal("99"), OrderSide.BUY, Decimal("0.005")
    )
    assert d.reason == "invalid_inputs"


# ── evaluate_entry: happy + gates ──
def test_evaluate_entry_approves() -> None:
    eng = RiskEngine(CFG)
    d = eng.evaluate_entry(_state(), _ctx())
    assert d.approved


def test_gate_killswitch() -> None:
    eng = RiskEngine(CFG)
    st = _state()
    st.killed = True
    assert eng.evaluate_entry(st, _ctx()).reason == "killswitch"


def test_gate_daily_stop() -> None:
    eng = RiskEngine(CFG)
    st = _state()
    st.day_pnl = Decimal("-200")  # -2% от 10000
    assert eng.evaluate_entry(st, _ctx()).reason == "daily_stop"


def test_gate_consecutive_losses() -> None:
    eng = RiskEngine(CFG)
    st = _state()
    st.consecutive_losses = CFG.max_consecutive_losses
    assert eng.evaluate_entry(st, _ctx()).reason == "consecutive_losses"


def test_gate_max_positions_total() -> None:
    eng = RiskEngine(CFG)
    st = _state()
    st.open_positions = [("A", "x"), ("B", "y"), ("C", "z")]
    assert eng.evaluate_entry(st, _ctx()).reason == "max_positions_total"


def test_gate_max_positions_per_class() -> None:
    eng = RiskEngine(CFG)
    st = _state()
    st.open_positions = [("A", "crypto"), ("B", "crypto")]
    assert eng.evaluate_entry(st, _ctx(symbol="C/USDT:USDT")).reason == "max_positions_per_class"


def test_gate_max_trades_per_day() -> None:
    eng = RiskEngine(CFG)
    st = _state()
    st.trades_today_total = CFG.max_trades_per_day
    assert eng.evaluate_entry(st, _ctx()).reason == "max_trades_per_day"


def test_gate_trade_interval() -> None:
    eng = RiskEngine(CFG)
    st = _state()
    st.last_trade_ts_by_symbol["BTC/USDT:USDT"] = 1_000_000.0 - 10
    assert eng.evaluate_entry(st, _ctx()).reason == "trade_interval"


def test_gate_spread_too_wide() -> None:
    eng = RiskEngine(CFG)
    d = eng.evaluate_entry(_state(), _ctx(spread=Decimal("10"), spread_median=Decimal("1")))
    assert d.reason == "spread_too_wide"


def test_gate_cost_edge() -> None:
    eng = RiskEngine(CFG)
    d = eng.evaluate_entry(_state(), _ctx(expected_tp_pct=Decimal("0.005")))
    assert d.reason == "cost_edge"


# ── state transitions ──
def test_update_equity_triggers_killswitch_at_15pct() -> None:
    st = _state()
    st.update_equity(Decimal("8400"), CFG)  # -16% от пика 10000
    assert st.killed is True


def test_update_equity_no_killswitch_above_threshold() -> None:
    st = _state()
    st.update_equity(Decimal("8600"), CFG)  # -14%
    assert st.killed is False


def test_register_close_loss_halts_day_and_counts() -> None:
    eng = RiskEngine(CFG)
    st = _state()
    eng.register_open(st, "BTC/USDT:USDT", "crypto", 1_000_000.0)
    eng.register_close(st, "BTC/USDT:USDT", Decimal("-250"), Decimal("9750"))
    assert st.consecutive_losses == 1
    assert st.day in st.halted_days  # -2.5% превысил дневной -2%
    assert st.open_positions == []


def test_register_close_profit_resets_streak() -> None:
    eng = RiskEngine(CFG)
    st = _state()
    st.consecutive_losses = 3
    eng.register_open(st, "BTC/USDT:USDT", "crypto", 1_000_000.0)
    eng.register_close(st, "BTC/USDT:USDT", Decimal("100"), Decimal("10100"))
    assert st.consecutive_losses == 0


def test_roll_period_resets_day() -> None:
    st = _state()
    st.day_pnl = Decimal("-100")
    st.trades_today_total = 5
    st.roll_period(date(2026, 5, 21))
    assert st.day_pnl == Decimal("0")
    assert st.trades_today_total == 0
