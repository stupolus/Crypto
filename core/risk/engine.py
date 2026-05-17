"""RiskEngine: расчёт размера + circuit breakers.

Чистая функция: ``evaluate(inputs) -> Approval | Rejection``. Без сети,
без persistence, без time.

Источник всех правил — `бизнес/риск-профиль.md`. Числа — в `config.yaml`.
"""

from __future__ import annotations

from decimal import Decimal

from core.risk.config import RiskConfig, get_default_config
from core.risk.models import (
    RejectionCode,
    RiskApproval,
    RiskDecision,
    RiskInputs,
    RiskRejection,
    RiskTier,
    Side,
)

_HUNDRED = Decimal("100")


def _risk_pct(config: RiskConfig, tier: RiskTier) -> Decimal:
    if tier == RiskTier.SCALP:
        return Decimal(str(config.risk_pct.SCALP))
    if tier == RiskTier.B:
        return Decimal(str(config.risk_pct.B))
    if tier == RiskTier.A:
        return Decimal(str(config.risk_pct.A))
    return Decimal(str(config.risk_pct.A_PLUS))


class RiskEngine:
    """Stateless risk-движок. Один inputs → одно решение."""

    def __init__(self, config: RiskConfig | None = None) -> None:
        self._config = config or get_default_config()

    @property
    def config(self) -> RiskConfig:
        return self._config

    def evaluate(self, inputs: RiskInputs) -> RiskDecision:
        cfg = self._config

        # Sanity-проверки на inputs уже частично сделаны pydantic'ом
        # (equity > 0, entry > 0, stop > 0, направление стопа). Здесь —
        # доменные проверки.

        # Stop too tight: < min_pct
        stop_distance = abs(inputs.entry_price - inputs.stop_price)
        stop_distance_pct = (stop_distance / inputs.entry_price) * _HUNDRED
        if stop_distance_pct < Decimal(str(cfg.limits.stop_min_pct)):
            return RiskRejection(
                code=RejectionCode.STOP_TOO_TIGHT,
                reason=(
                    f"stop distance {stop_distance_pct:.4f}% < min "
                    f"{cfg.limits.stop_min_pct}% (риск-профиль.md)"
                ),
                details={
                    "stop_distance_pct": format(stop_distance_pct, "f"),
                    "min_pct": str(cfg.limits.stop_min_pct),
                },
            )

        # Circuit breakers (любой = отказ).
        breaker = self._circuit_breakers(inputs)
        if breaker is not None:
            return breaker

        # SCALP-профиль: backtest-gate + fee-edge-gate + лимиты частоты.
        if inputs.tier == RiskTier.SCALP:
            scalp_reject = self._scalp_gates(inputs)
            if scalp_reject is not None:
                return scalp_reject

        # Размер позиции.
        risk_pct = _risk_pct(cfg, inputs.tier)
        notional = (inputs.equity * risk_pct) / stop_distance_pct
        quantity = notional / inputs.entry_price
        effective_leverage = notional / inputs.equity

        # Leverage cap.
        max_lev = Decimal(str(cfg.limits.max_effective_leverage))
        if effective_leverage > max_lev:
            return RiskRejection(
                code=RejectionCode.LEVERAGE_OVER_CAP,
                reason=(
                    f"effective_leverage {effective_leverage:.4f}x > cap "
                    f"{max_lev}x (риск-профиль.md)"
                ),
                details={
                    "effective_leverage": format(effective_leverage, "f"),
                    "cap": str(max_lev),
                },
            )

        # Liquidation buffer (если задан).
        if inputs.liquidation_price is not None:
            liq_check = self._check_liquidation_buffer(inputs, stop_distance)
            if liq_check is not None:
                return liq_check

        return RiskApproval(
            quantity=quantity,
            notional=notional,
            effective_leverage=effective_leverage,
            stop_distance_pct=stop_distance_pct,
            tier=inputs.tier,
        )

    def _circuit_breakers(self, inputs: RiskInputs) -> RiskRejection | None:
        cfg = self._config.circuit_breakers
        # daily P&L
        daily_threshold = inputs.equity * Decimal(str(cfg.daily_loss_pct)) / _HUNDRED
        if inputs.day_pnl <= daily_threshold:
            return RiskRejection(
                code=RejectionCode.DAILY_LOSS_LIMIT,
                reason=(
                    f"day_pnl {inputs.day_pnl} <= {daily_threshold} ({cfg.daily_loss_pct}% эквити)"
                ),
                details={
                    "day_pnl": format(inputs.day_pnl, "f"),
                    "threshold": format(daily_threshold, "f"),
                },
            )
        # daily trades count
        if inputs.day_trades_count >= cfg.max_daily_trades:
            return RiskRejection(
                code=RejectionCode.DAILY_TRADES_LIMIT,
                reason=(
                    f"day_trades_count {inputs.day_trades_count} >= max {cfg.max_daily_trades}"
                ),
                details={"day_trades_count": str(inputs.day_trades_count)},
            )
        # consecutive losses
        if inputs.consecutive_losses >= cfg.max_consecutive_losses:
            return RiskRejection(
                code=RejectionCode.CONSECUTIVE_LOSSES,
                reason=(
                    f"consecutive_losses {inputs.consecutive_losses} >= "
                    f"max {cfg.max_consecutive_losses}"
                ),
                details={"consecutive_losses": str(inputs.consecutive_losses)},
            )
        # weekly
        if inputs.week_pnl is not None:
            weekly_threshold = inputs.equity * Decimal(str(cfg.weekly_loss_pct)) / _HUNDRED
            if inputs.week_pnl <= weekly_threshold:
                return RiskRejection(
                    code=RejectionCode.WEEKLY_LOSS_LIMIT,
                    reason=(
                        f"week_pnl {inputs.week_pnl} <= {weekly_threshold} "
                        f"({cfg.weekly_loss_pct}% эквити)"
                    ),
                    details={
                        "week_pnl": format(inputs.week_pnl, "f"),
                        "threshold": format(weekly_threshold, "f"),
                    },
                )
        # monthly
        if inputs.month_pnl is not None:
            monthly_threshold = inputs.equity * Decimal(str(cfg.monthly_loss_pct)) / _HUNDRED
            if inputs.month_pnl <= monthly_threshold:
                return RiskRejection(
                    code=RejectionCode.MONTHLY_LOSS_LIMIT,
                    reason=(
                        f"month_pnl {inputs.month_pnl} <= {monthly_threshold} "
                        f"({cfg.monthly_loss_pct}% эквити)"
                    ),
                    details={
                        "month_pnl": format(inputs.month_pnl, "f"),
                        "threshold": format(monthly_threshold, "f"),
                    },
                )
        return None

    def _scalp_gates(self, inputs: RiskInputs) -> RiskRejection | None:
        """Гейты, специфичные для SCALP-профиля.

        1. backtest-gate: пока `scalp.enabled=false` — скальп запрещён
           (включается только после зелёного бэктеста, план 22.4).
        2. fee-edge-gate: TP должен покрывать трение с запасом
           (`TP% >= k × trade_cost%`), иначе edge съедается комиссией.
        3. лимиты частоты: число скальп-сделок/позиций.
        Все числа — `бизнес/риск-профиль.md` / `правила-скальпинга.md`.
        """
        scfg = self._config.scalp

        if not scfg.enabled:
            return RiskRejection(
                code=RejectionCode.SCALP_DISABLED,
                reason=(
                    "SCALP отключён (scalp.enabled=false). Включается после "
                    "зелёного бэктеста — план 22.4 / правила-скальпинга.md"
                ),
            )

        if inputs.scalp_trades_today >= scfg.max_scalp_trades_day:
            return RiskRejection(
                code=RejectionCode.SCALP_TRADES_LIMIT,
                reason=(
                    f"scalp_trades_today {inputs.scalp_trades_today} >= max "
                    f"{scfg.max_scalp_trades_day}"
                ),
                details={"scalp_trades_today": str(inputs.scalp_trades_today)},
            )

        if inputs.scalp_positions_open >= scfg.max_scalp_positions:
            return RiskRejection(
                code=RejectionCode.SCALP_POSITIONS_LIMIT,
                reason=(
                    f"scalp_positions_open {inputs.scalp_positions_open} >= max "
                    f"{scfg.max_scalp_positions}"
                ),
                details={"scalp_positions_open": str(inputs.scalp_positions_open)},
            )

        if inputs.take_profit_price is None:
            return RiskRejection(
                code=RejectionCode.SCALP_NO_EDGE,
                reason="SCALP требует take_profit_price для fee-edge-gate",
            )

        tp_distance = abs(inputs.take_profit_price - inputs.entry_price)
        tp_pct = (tp_distance / inputs.entry_price) * _HUNDRED
        required = Decimal(str(scfg.fee_edge_k)) * Decimal(str(scfg.trade_cost_pct))
        if tp_pct < required:
            return RiskRejection(
                code=RejectionCode.SCALP_NO_EDGE,
                reason=(
                    f"tp {tp_pct:.4f}% < required {required}% "
                    f"(k={scfg.fee_edge_k} × trade_cost={scfg.trade_cost_pct}%)"
                ),
                details={
                    "tp_pct": format(tp_pct, "f"),
                    "required_pct": format(required, "f"),
                },
            )
        return None

    def _check_liquidation_buffer(
        self, inputs: RiskInputs, stop_distance: Decimal
    ) -> RiskRejection | None:
        """Цена ликвидации должна быть **дальше** стопа от entry, причём
        с buffer'ом ≥ 30% от расстояния до стопа.

        Логика: при срабатывании стопа мы теряем `stop_distance`. Если
        ликвидация прямо за стопом — рывок цены через стоп может ликвиднуть
        позицию вместо обычного market-close. Buffer защищает.
        """
        assert inputs.liquidation_price is not None
        cfg = self._config.limits
        buffer_required = stop_distance * Decimal(str(cfg.liquidation_buffer_ratio))

        if inputs.side == Side.LONG:
            # LONG: liquidation ниже stop, оба ниже entry.
            buffer = inputs.stop_price - inputs.liquidation_price
        else:
            # SHORT: liquidation выше stop, оба выше entry.
            buffer = inputs.liquidation_price - inputs.stop_price

        if buffer < buffer_required:
            return RiskRejection(
                code=RejectionCode.LIQUIDATION_TOO_CLOSE,
                reason=(
                    f"liquidation buffer {buffer} < required {buffer_required} "
                    f"({cfg.liquidation_buffer_ratio * 100}% от расстояния стопа)"
                ),
                details={
                    "buffer": format(buffer, "f"),
                    "required": format(buffer_required, "f"),
                },
            )
        return None
