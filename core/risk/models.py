"""Доменные модели RiskEngine.

Stateless inputs/outputs: чистая функция ``evaluate`` принимает
``RiskInputs`` и возвращает ``RiskDecision`` (Approval | Rejection).
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RiskTier(StrEnum):
    """Tier сетапа определяет risk_pct.

    SCALP — скальп-профиль (мелкий риск, тонкий стоп, fee-edge-gate).
    B — стандартный. A — подтверждённый. A+ — премиум.
    Решение о tier'е принимает стратегия и передаёт в RiskInputs.
    Все числа — `бизнес/риск-профиль.md`.
    """

    SCALP = "SCALP"
    B = "B"
    A = "A"
    A_PLUS = "A+"


class Side(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RiskInputs(_Frozen):
    """Все данные, которые нужны для одного решения.

    Stateful-учёт (P&L за день / неделю / месяц, счётчик сделок) —
    задача orchestrator (или strategy-runner). RiskEngine получает
    готовые числа.
    """

    equity: Decimal = Field(gt=0)
    day_pnl: Decimal = Field(default=Decimal("0"))
    day_trades_count: int = Field(default=0, ge=0)
    consecutive_losses: int = Field(default=0, ge=0)
    week_pnl: Decimal | None = None
    month_pnl: Decimal | None = None

    # Счётчики скальпа ведёт orchestrator, движок только проверяет.
    scalp_trades_today: int = Field(default=0, ge=0)
    scalp_positions_open: int = Field(default=0, ge=0)

    side: Side
    entry_price: Decimal = Field(gt=0)
    stop_price: Decimal = Field(gt=0)
    # Нужен для SCALP fee-edge-gate (TP должен отбивать трение). Для
    # свинговых tier'ов опционален.
    take_profit_price: Decimal | None = None
    tier: RiskTier = RiskTier.B
    # Опц.: если задано, проверим buffer до ликвидации. Адаптер может
    # отдать его из /user/positions после открытия первой позиции.
    liquidation_price: Decimal | None = None

    @model_validator(mode="after")
    def _check_stop_direction(self) -> RiskInputs:
        if self.side == Side.LONG and self.stop_price >= self.entry_price:
            raise ValueError(
                f"LONG stop must be below entry, got stop={self.stop_price} "
                f"entry={self.entry_price}"
            )
        if self.side == Side.SHORT and self.stop_price <= self.entry_price:
            raise ValueError(
                f"SHORT stop must be above entry, got stop={self.stop_price} "
                f"entry={self.entry_price}"
            )
        if self.take_profit_price is not None:
            if self.side == Side.LONG and self.take_profit_price <= self.entry_price:
                raise ValueError(
                    f"LONG take-profit must be above entry, got "
                    f"tp={self.take_profit_price} entry={self.entry_price}"
                )
            if self.side == Side.SHORT and self.take_profit_price >= self.entry_price:
                raise ValueError(
                    f"SHORT take-profit must be below entry, got "
                    f"tp={self.take_profit_price} entry={self.entry_price}"
                )
        return self


class RiskApproval(_Frozen):
    """Положительное решение: что отправлять на биржу."""

    quantity: Decimal  # в базовой валюте (например, BTC)
    notional: Decimal  # в USDT
    effective_leverage: Decimal
    stop_distance_pct: Decimal  # |entry - stop| / entry × 100
    tier: RiskTier


class RejectionCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    INVALID_STOP = "INVALID_STOP"
    STOP_TOO_TIGHT = "STOP_TOO_TIGHT"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    DAILY_TRADES_LIMIT = "DAILY_TRADES_LIMIT"
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    WEEKLY_LOSS_LIMIT = "WEEKLY_LOSS_LIMIT"
    MONTHLY_LOSS_LIMIT = "MONTHLY_LOSS_LIMIT"
    LEVERAGE_OVER_CAP = "LEVERAGE_OVER_CAP"
    LIQUIDATION_TOO_CLOSE = "LIQUIDATION_TOO_CLOSE"
    SCALP_DISABLED = "SCALP_DISABLED"
    SCALP_NO_EDGE = "SCALP_NO_EDGE"
    SCALP_TRADES_LIMIT = "SCALP_TRADES_LIMIT"
    SCALP_POSITIONS_LIMIT = "SCALP_POSITIONS_LIMIT"


class RiskRejection(_Frozen):
    """Отказ. ``code`` машинно-читаемый, ``reason`` — для логов."""

    code: RejectionCode
    reason: str
    details: dict[str, str] = Field(default_factory=dict)


RiskDecision = RiskApproval | RiskRejection
