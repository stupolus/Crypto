"""Модели для Layer 6 Post-Mortem (plan #18).

``TradeOutcome`` — единая запись о закрытой сделке вместе со всем
контекстом, который привёл к её открытию (signal candidate, ответы
субагентов, coordinator decision, macro snapshot).

После закрытия каждой сделки runner вызовет
``TradeOutcomeLogger.record_exit`` (отдельный PR подключит реализацию
через SQLite). Hot path → запись. Постмортем (Mistake Library, Past-
Mistakes Context Injector) работает offline над этой таблицей.

Все числовые поля — строки (Decimal-friendly), чтобы legkо
сериализовывать в JSON и хранить в SQLite без потери точности.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ExitReason = Literal[
    "TP1",
    "TP2",
    "SL",
    "TIMEOUT",
    "MANUAL",
    "RISK_OFF",
]

OrderSide = Literal["BUY", "SELL"]


class TradeOutcome(BaseModel):
    """Полная запись о закрытой сделке для Layer 6 анализа.

    Hot path заполняет entry-fields при открытии (``record_entry``),
    exit-fields при закрытии (``record_exit``). Между этими событиями
    запись в "open" состоянии (``exit_time_ms is None``).

    LLM context snapshot хранится как JSON-строки — runner serialize'ет
    payload'ы субагентов сразу после coordinator decision, чтобы не
    тянуть mutable state.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    trade_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: OrderSide

    # Entry data (известно сразу)
    entry_time_ms: int = Field(gt=0)
    entry_price: Decimal = Field(gt=Decimal("0"))
    size: Decimal = Field(gt=Decimal("0"))

    # Exit data (заполняется после закрытия; None пока сделка открыта)
    exit_time_ms: int | None = Field(default=None, gt=0)
    exit_price: Decimal | None = Field(default=None, gt=Decimal("0"))
    pnl_usd: Decimal | None = None
    pnl_pct: Decimal | None = None
    exit_reason: ExitReason | None = None
    holding_time_min: int | None = Field(default=None, ge=0)

    # LLM context (snapshot at decision time) — JSON-сериализованные dict-ы
    signal_candidate_json: str = Field(min_length=2, description="JSON SignalCandidate")
    market_analyst_json: str = Field(min_length=2)
    sentiment_analyst_json: str = Field(min_length=2)
    risk_overseer_json: str = Field(min_length=2)
    macro_analyst_json: str = Field(min_length=2)
    coordinator_json: str = Field(min_length=2)

    # Performance metrics (опциональны — runner может не успеть)
    latency_decision_ms: int | None = Field(default=None, ge=0)
    latency_execution_ms: int | None = Field(default=None, ge=0)
    slippage_bps: Decimal | None = None

    @property
    def is_closed(self) -> bool:
        """True если сделка закрыта (exit-данные заполнены)."""
        return self.exit_time_ms is not None and self.exit_price is not None

    @property
    def is_loss(self) -> bool:
        """True если закрытая сделка убыточна. Open / breakeven → False."""
        return self.pnl_pct is not None and self.pnl_pct < Decimal("0")

    @property
    def is_win(self) -> bool:
        return self.pnl_pct is not None and self.pnl_pct > Decimal("0")

    @model_validator(mode="after")
    def _check_exit_invariants(self) -> TradeOutcome:
        """Если exit_time или exit_price есть — оба должны быть, и > entry_time.

        Open trade: оба None. Closed trade: оба не-None.
        Mixed состояние недопустимо.
        """
        if (self.exit_time_ms is None) != (self.exit_price is None):
            raise ValueError("exit_time_ms и exit_price должны быть оба None или оба set")
        if self.exit_time_ms is not None and self.exit_time_ms < self.entry_time_ms:
            raise ValueError(
                f"exit_time_ms ({self.exit_time_ms}) < entry_time_ms ({self.entry_time_ms})"
            )
        return self


class ExitData(BaseModel):
    """Bundle полей для record_exit — закрывает существующую TradeOutcome.

    Удобный wrapper чтобы runner не строил полный TradeOutcome заново.
    Logger сам объединит entry+exit на уровне SQL UPDATE.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    exit_time_ms: int = Field(gt=0)
    exit_price: Decimal = Field(gt=Decimal("0"))
    pnl_usd: Decimal
    pnl_pct: Decimal
    exit_reason: ExitReason
    holding_time_min: int = Field(ge=0)
    slippage_bps: Decimal | None = None


class DecisionContext(BaseModel):
    """Bundle того, что нужно сохранить при открытии сделки.

    Содержит SignalCandidate + payload'ы всех 5 субагентов + coordinator.
    Runner строит это при срабатывании llm_gate и передаёт в logger.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    trade_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    side: OrderSide
    entry_time_ms: int = Field(gt=0)
    entry_price: Decimal = Field(gt=Decimal("0"))
    size: Decimal = Field(gt=Decimal("0"))

    signal_candidate: dict[str, Any]
    market_analyst: dict[str, Any]
    sentiment_analyst: dict[str, Any]
    risk_overseer: dict[str, Any]
    macro_analyst: dict[str, Any]
    coordinator: dict[str, Any]

    latency_decision_ms: int | None = Field(default=None, ge=0)
