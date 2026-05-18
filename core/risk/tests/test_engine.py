"""Unit-тесты ``core.risk.engine.RiskEngine``."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.risk import (
    RejectionCode,
    RiskApproval,
    RiskConfig,
    RiskEngine,
    RiskInputs,
    RiskRejection,
    RiskTier,
    Side,
)


@pytest.fixture
def engine() -> RiskEngine:
    return RiskEngine()


def _base_inputs(
    *,
    equity: Decimal = Decimal("1000"),
    entry: Decimal = Decimal("60000"),
    stop: Decimal = Decimal("59400"),  # -1.0% от entry
    side: Side = Side.LONG,
    tier: RiskTier = RiskTier.B,
    day_pnl: Decimal = Decimal("0"),
    day_trades_count: int = 0,
    consecutive_losses: int = 0,
    week_pnl: Decimal | None = None,
    month_pnl: Decimal | None = None,
    liquidation_price: Decimal | None = None,
    take_profit_price: Decimal | None = None,
    scalp_trades_today: int = 0,
    scalp_positions_open: int = 0,
) -> RiskInputs:
    return RiskInputs(
        equity=equity,
        entry_price=entry,
        stop_price=stop,
        side=side,
        tier=tier,
        day_pnl=day_pnl,
        day_trades_count=day_trades_count,
        consecutive_losses=consecutive_losses,
        week_pnl=week_pnl,
        month_pnl=month_pnl,
        liquidation_price=liquidation_price,
        take_profit_price=take_profit_price,
        scalp_trades_today=scalp_trades_today,
        scalp_positions_open=scalp_positions_open,
    )


def _scalp_engine(*, enabled: bool = True) -> RiskEngine:
    """Движок с дефолтными числами, но включённым скальпом (для тестов
    fee-edge-gate и лимитов; на проде scalp.enabled=false — backtest-gate)."""
    cfg = RiskConfig.model_validate(
        {
            "risk_pct": {"SCALP": 0.75, "B": 1.5, "A": 2.0, "A_PLUS": 3.0},
            "limits": {
                "max_effective_leverage": 10,
                "stop_min_pct": 0.15,
                "liquidation_buffer_ratio": 0.3,
                "maintenance_margin_rate": 0.01,
            },
            "circuit_breakers": {
                "daily_loss_pct": -5.0,
                "weekly_loss_pct": -10.0,
                "monthly_loss_pct": -20.0,
                "max_daily_trades": 25,
                "max_consecutive_losses": 5,
            },
            "scalp": {
                "enabled": enabled,
                "fee_edge_k": 2.0,
                "trade_cost_pct": 0.15,
                "max_scalp_positions": 2,
                "max_scalp_trades_day": 25,
            },
        }
    )
    return RiskEngine(cfg)


# ── Approvals ────────────────────────────────────────────────────────────


def test_approval_b_tier_default(engine: RiskEngine) -> None:
    """Депозит $1000, B=1.5% риск, стоп 1% → notional $1500, leverage 1.5x."""
    decision = engine.evaluate(_base_inputs())
    assert isinstance(decision, RiskApproval)
    # risk_pct=1.5, stop_distance_pct=1.0 → notional = 1000*1.5/1 = 1500.
    assert decision.notional == Decimal("1500")
    assert decision.effective_leverage == Decimal("1.5")
    assert decision.quantity == Decimal("1500") / Decimal("60000")
    assert decision.tier == RiskTier.B


def test_approval_a_plus_doubles_size(engine: RiskEngine) -> None:
    """A+ (3.0%) vs B (1.5%) → ровно 2x notional."""
    b = engine.evaluate(_base_inputs(tier=RiskTier.B))
    aplus = engine.evaluate(_base_inputs(tier=RiskTier.A_PLUS))
    assert isinstance(b, RiskApproval)
    assert isinstance(aplus, RiskApproval)
    assert aplus.notional == b.notional * Decimal("2")


def test_approval_short_side(engine: RiskEngine) -> None:
    decision = engine.evaluate(
        _base_inputs(
            side=Side.SHORT,
            entry=Decimal("60000"),
            stop=Decimal("60600"),  # +1% от entry
        )
    )
    assert isinstance(decision, RiskApproval)


def test_approval_without_liquidation_price_skips_buffer_check(
    engine: RiskEngine,
) -> None:
    """Без `liquidation_price` проверка skip — это explicit decision."""
    decision = engine.evaluate(_base_inputs())  # без liquidation_price
    assert isinstance(decision, RiskApproval)


# ── Rejections — sanity / pydantic ─────────────────────────────────────────


def test_pydantic_rejects_long_with_stop_above_entry() -> None:
    with pytest.raises(ValueError, match="LONG stop must be below"):
        _base_inputs(stop=Decimal("60001"))


def test_pydantic_rejects_short_with_stop_below_entry() -> None:
    with pytest.raises(ValueError, match="SHORT stop must be above"):
        _base_inputs(side=Side.SHORT, stop=Decimal("59999"))


def test_pydantic_rejects_zero_equity() -> None:
    with pytest.raises(ValueError):
        _base_inputs(equity=Decimal("0"))


def test_pydantic_rejects_long_tp_below_entry() -> None:
    with pytest.raises(ValueError, match="LONG take-profit must be above"):
        _base_inputs(take_profit_price=Decimal("59999"))


def test_pydantic_rejects_short_tp_above_entry() -> None:
    with pytest.raises(ValueError, match="SHORT take-profit must be below"):
        _base_inputs(
            side=Side.SHORT,
            stop=Decimal("60600"),
            take_profit_price=Decimal("60001"),
        )


# ── Rejections — domain ───────────────────────────────────────────────────


def test_reject_stop_too_tight(engine: RiskEngine) -> None:
    """Стоп 0.1% < 0.15% min → STOP_TOO_TIGHT."""
    decision = engine.evaluate(_base_inputs(entry=Decimal("60000"), stop=Decimal("59940")))
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.STOP_TOO_TIGHT


def test_reject_daily_loss_limit(engine: RiskEngine) -> None:
    decision = engine.evaluate(
        _base_inputs(day_pnl=Decimal("-50"))  # -5% от 1000
    )
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.DAILY_LOSS_LIMIT


def test_reject_daily_trades_limit(engine: RiskEngine) -> None:
    decision = engine.evaluate(_base_inputs(day_trades_count=25))
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.DAILY_TRADES_LIMIT


def test_reject_consecutive_losses(engine: RiskEngine) -> None:
    decision = engine.evaluate(_base_inputs(consecutive_losses=5))
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.CONSECUTIVE_LOSSES


def test_reject_weekly_loss_limit(engine: RiskEngine) -> None:
    decision = engine.evaluate(_base_inputs(week_pnl=Decimal("-100")))  # -10%
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.WEEKLY_LOSS_LIMIT


def test_reject_monthly_loss_limit(engine: RiskEngine) -> None:
    decision = engine.evaluate(_base_inputs(month_pnl=Decimal("-200")))  # -20%
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.MONTHLY_LOSS_LIMIT


def test_reject_leverage_over_cap() -> None:
    """risk 5% + стоп 0.5% → notional 10000 → leverage 10x > cap 5x."""
    cfg = RiskConfig.model_validate(
        {
            "risk_pct": {"SCALP": 5.0, "B": 5.0, "A": 5.0, "A_PLUS": 5.0},
            "limits": {
                "max_effective_leverage": 5,
                "stop_min_pct": 0.5,
                "liquidation_buffer_ratio": 0.3,
                "maintenance_margin_rate": 0.01,
            },
            "circuit_breakers": {
                "daily_loss_pct": -5.0,
                "weekly_loss_pct": -10.0,
                "monthly_loss_pct": -20.0,
                "max_daily_trades": 25,
                "max_consecutive_losses": 5,
            },
            "scalp": {
                "enabled": False,
                "fee_edge_k": 2.0,
                "trade_cost_pct": 0.15,
                "max_scalp_positions": 2,
                "max_scalp_trades_day": 25,
            },
        }
    )
    custom_engine = RiskEngine(cfg)
    # risk 5% + stop 0.5% → notional = 1000 * 5 / 0.5 = 10000 → leverage 10x.
    decision = custom_engine.evaluate(_base_inputs(stop=Decimal("59700")))
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.LEVERAGE_OVER_CAP


def test_reject_liquidation_too_close_long(engine: RiskEngine) -> None:
    """LONG: liquidation в 10% за стопом при стопе 1% — buffer < 30%."""
    decision = engine.evaluate(_base_inputs(liquidation_price=Decimal("59300")))
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.LIQUIDATION_TOO_CLOSE


def test_approval_with_sufficient_liquidation_buffer(engine: RiskEngine) -> None:
    """LONG: liquidation в 50% за стопом — buffer ≫ 30%."""
    decision = engine.evaluate(_base_inputs(liquidation_price=Decimal("59100")))
    assert isinstance(decision, RiskApproval)


def test_reject_liquidation_too_close_short(engine: RiskEngine) -> None:
    """SHORT: симметрия. entry=60000, stop=60600, liq=60700 → buffer 100 < 180."""
    decision = engine.evaluate(
        _base_inputs(
            side=Side.SHORT,
            entry=Decimal("60000"),
            stop=Decimal("60600"),
            liquidation_price=Decimal("60700"),
        )
    )
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.LIQUIDATION_TOO_CLOSE


# ── SCALP-профиль ─────────────────────────────────────────────────────────


def test_scalp_disabled_by_default(engine: RiskEngine) -> None:
    """Дефолтный config: scalp.enabled=false → SCALP_DISABLED (backtest-gate)."""
    decision = engine.evaluate(
        _base_inputs(tier=RiskTier.SCALP, take_profit_price=Decimal("60300"))
    )
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.SCALP_DISABLED


def test_scalp_requires_take_profit() -> None:
    decision = _scalp_engine().evaluate(_base_inputs(tier=RiskTier.SCALP))
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.SCALP_NO_EDGE


def test_scalp_fee_edge_gate_rejects_thin_tp() -> None:
    """TP 0.2% < required 0.30% (k=2 × cost=0.15) → SCALP_NO_EDGE."""
    decision = _scalp_engine().evaluate(
        _base_inputs(tier=RiskTier.SCALP, take_profit_price=Decimal("60120"))  # +0.2%
    )
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.SCALP_NO_EDGE


def test_scalp_fee_edge_gate_passes_with_sufficient_tp() -> None:
    """TP 0.4% >= required 0.30% → одобрено, tier SCALP, risk 0.75%."""
    decision = _scalp_engine().evaluate(
        _base_inputs(
            tier=RiskTier.SCALP,
            stop=Decimal("59820"),  # -0.3% (>= 0.15 min)
            take_profit_price=Decimal("60240"),  # +0.4%
        )
    )
    assert isinstance(decision, RiskApproval)
    assert decision.tier == RiskTier.SCALP
    # risk 0.75%, stop 0.3% → notional = 1000 * 0.75 / 0.3 = 2500.
    assert decision.notional == Decimal("2500")


def test_scalp_trades_limit() -> None:
    decision = _scalp_engine().evaluate(
        _base_inputs(
            tier=RiskTier.SCALP,
            take_profit_price=Decimal("60240"),
            scalp_trades_today=25,
        )
    )
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.SCALP_TRADES_LIMIT


def test_scalp_positions_limit() -> None:
    decision = _scalp_engine().evaluate(
        _base_inputs(
            tier=RiskTier.SCALP,
            take_profit_price=Decimal("60240"),
            scalp_positions_open=2,
        )
    )
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.SCALP_POSITIONS_LIMIT


# ── Properties / regression ──────────────────────────────────────────────


def test_notional_scales_linearly_with_equity(engine: RiskEngine) -> None:
    """При увеличении эквити в 10x — notional в 10x."""
    small = engine.evaluate(_base_inputs(equity=Decimal("1000")))
    big = engine.evaluate(_base_inputs(equity=Decimal("10000")))
    assert isinstance(small, RiskApproval)
    assert isinstance(big, RiskApproval)
    assert big.notional == small.notional * Decimal("10")


def test_notional_inversely_with_stop_distance(engine: RiskEngine) -> None:
    """При увеличении расстояния стопа в 2x — notional в 2x меньше."""
    close = engine.evaluate(
        _base_inputs(entry=Decimal("60000"), stop=Decimal("59400"))  # 1%
    )
    far = engine.evaluate(
        _base_inputs(entry=Decimal("60000"), stop=Decimal("58800"))  # 2%
    )
    assert isinstance(close, RiskApproval)
    assert isinstance(far, RiskApproval)
    assert close.notional == far.notional * Decimal("2")
