"""Unit-тесты ``core.risk.engine.RiskEngine``."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.risk import (
    RejectionCode,
    RiskApproval,
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
    )


# ── Approvals ────────────────────────────────────────────────────────────


def test_approval_b_tier_default(engine: RiskEngine) -> None:
    """Депозит $1000, 1% риск, стоп 1% → notional $1000, leverage 1x."""
    decision = engine.evaluate(_base_inputs())
    assert isinstance(decision, RiskApproval)
    # risk_pct=1.0, stop_distance_pct=1.0 → notional = 1000*1/1 = 1000.
    assert decision.notional == Decimal("1000")
    assert decision.effective_leverage == Decimal("1")
    # quantity = 1000 / 60000 = 0.01666...
    assert decision.quantity == Decimal("1000") / Decimal("60000")
    assert decision.tier == RiskTier.B


def test_approval_a_plus_doubles_size(engine: RiskEngine) -> None:
    """A+ tier удваивает notional vs B-tier."""
    b = engine.evaluate(_base_inputs(tier=RiskTier.B))
    aplus = engine.evaluate(_base_inputs(tier=RiskTier.A_PLUS))
    assert isinstance(b, RiskApproval)
    assert isinstance(aplus, RiskApproval)
    # 2.0 / 1.0 = 2x
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


# ── Rejections — domain ───────────────────────────────────────────────────


def test_reject_stop_too_tight(engine: RiskEngine) -> None:
    """Стоп 0.3% < 0.5% min → STOP_TOO_TIGHT."""
    decision = engine.evaluate(
        _base_inputs(entry=Decimal("60000"), stop=Decimal("59820"))
    )
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.STOP_TOO_TIGHT


def test_reject_daily_loss_limit(engine: RiskEngine) -> None:
    decision = engine.evaluate(
        _base_inputs(day_pnl=Decimal("-30"))  # -3% от 1000
    )
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.DAILY_LOSS_LIMIT


def test_reject_daily_trades_limit(engine: RiskEngine) -> None:
    decision = engine.evaluate(_base_inputs(day_trades_count=3))
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.DAILY_TRADES_LIMIT


def test_reject_consecutive_losses(engine: RiskEngine) -> None:
    decision = engine.evaluate(_base_inputs(consecutive_losses=3))
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.CONSECUTIVE_LOSSES


def test_reject_weekly_loss_limit(engine: RiskEngine) -> None:
    decision = engine.evaluate(_base_inputs(week_pnl=Decimal("-70")))  # -7%
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.WEEKLY_LOSS_LIMIT


def test_reject_monthly_loss_limit(engine: RiskEngine) -> None:
    decision = engine.evaluate(_base_inputs(month_pnl=Decimal("-150")))  # -15%
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.MONTHLY_LOSS_LIMIT


def test_reject_leverage_over_cap(engine: RiskEngine) -> None:
    """1% риск, стоп 0.15% → нужно ~6.67x → LEVERAGE_OVER_CAP."""
    # Минимум 0.5% — не позволит. Тогда: 1% риск + stop=0.6% → leverage 1.67x (OK).
    # Нужен сценарий с большим notional. Возьмём A+ (2%) и стоп 0.5%:
    # notional = 1000 * 2 / 0.5 = 4000 → leverage 4x. Тоже под cap.
    # A+ риск 2% + стоп 0.39% — недопустим (< 0.5%).
    # Реальный путь: A+ риск 2% + стоп 0.5% min, leverage 4x. Чтобы получить
    # > 5x, нужно risk_pct > 2.5% или stop < 0.4% (нельзя).
    # Альтернатива: 2 параллельные позиции не покрываются RiskEngine MVP.
    # Сценарий: equity мал → notional > equity * 5. Но формула notional не
    # привязана к equity, leverage = notional/equity. Если risk_pct=2%,
    # stop=0.4% — недопустимо (STOP_TOO_TIGHT). На MVP leverage_cap эффективно
    # достижим только если разрешить stop_min_pct < 0.4% или risk_pct > 2.5%.
    # Проверим логику: создадим custom config через monkeypatch.
    from core.risk.config import RiskConfig

    cfg = RiskConfig.model_validate(
        {
            "risk_pct": {"B": 5.0, "A": 5.0, "A_PLUS": 5.0},  # высокий риск
            "limits": {
                "max_effective_leverage": 5,
                "stop_min_pct": 0.5,
                "liquidation_buffer_ratio": 0.3,
            },
            "circuit_breakers": {
                "daily_loss_pct": -3.0,
                "weekly_loss_pct": -7.0,
                "monthly_loss_pct": -15.0,
                "max_daily_trades": 3,
                "max_consecutive_losses": 3,
            },
        }
    )
    custom_engine = RiskEngine(cfg)
    # risk 5% + stop 0.5% → notional = 1000 * 5 / 0.5 = 10000 → leverage 10x → reject.
    decision = custom_engine.evaluate(_base_inputs(stop=Decimal("59700")))
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.LEVERAGE_OVER_CAP


def test_reject_liquidation_too_close_long(engine: RiskEngine) -> None:
    """LONG: liquidation в 10% за стопом при стопе 1% — buffer < 30%."""
    # entry=60000, stop=59400 (-1%), liq=59300 → buffer=100, требуется 180.
    decision = engine.evaluate(
        _base_inputs(liquidation_price=Decimal("59300"))
    )
    assert isinstance(decision, RiskRejection)
    assert decision.code == RejectionCode.LIQUIDATION_TOO_CLOSE


def test_approval_with_sufficient_liquidation_buffer(engine: RiskEngine) -> None:
    """LONG: liquidation в 50% за стопом — buffer ≫ 30%."""
    decision = engine.evaluate(
        _base_inputs(liquidation_price=Decimal("59100"))
    )
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
