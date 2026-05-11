"""Доменные модели backtester."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

from adapters.bingx.models import Kline
from adapters.bingx.private_models import OrderRequest, OrderSide

FillReason = Literal[
    "ENTRY",
    "STOP_LOSS",
    "TAKE_PROFIT_1",
    "TRAILING_EXIT",
    "MANUAL_CLOSE",
]


@dataclass(frozen=True)
class FillEvent:
    """Симулированное исполнение."""

    timestamp_ms: int
    side: OrderSide
    price: Decimal
    quantity: Decimal
    fee: Decimal
    reason: FillReason


@dataclass(frozen=True)
class Trade:
    """Завершённая сделка: entry + 1..N exits."""

    entry: FillEvent
    exits: tuple[FillEvent, ...]
    pnl: Decimal           # USDT, с учётом fees
    pnl_pct: Decimal       # относительно entry notional
    duration_ms: int
    max_favorable_excursion_pct: Decimal
    max_adverse_excursion_pct: Decimal

    @property
    def is_win(self) -> bool:
        return self.pnl > 0

    @property
    def is_loss(self) -> bool:
        return self.pnl < 0


@dataclass(frozen=True)
class OpenPosition:
    """Текущая открытая позиция (для view стратегии)."""

    entry_price: Decimal
    quantity: Decimal           # > 0 для LONG, < 0 для SHORT
    side: OrderSide
    stop_price: Decimal
    take_profit_price: Decimal | None
    entry_time_ms: int


@dataclass(frozen=True)
class StrategyContext:
    """Read-only view стратегии. Никаких setters — стратегия не мутирует state."""

    current_candle: Kline
    history: Sequence[Kline]      # все закрытые свечи до и включая current
    equity: Decimal
    open_position: OpenPosition | None


@runtime_checkable
class Strategy(Protocol):
    """Контракт стратегии.

    ``on_candle_close`` — возвращает ``OrderRequest`` если хочет открыть
    позицию. ``None`` = ничего не делать. Если позиция уже открыта —
    backtester игнорирует возвращённый OrderRequest (запрет flip без
    закрытия предыдущей позиции; план 08 §3.8).

    ``on_fill`` — информирование. Стратегия может вести свой state
    (например, прибавлять/вычитать P&L) — но это не обязательно.
    """

    def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None: ...

    def on_fill(self, fill: FillEvent) -> None: ...


@dataclass(frozen=True)
class BacktestSummary:
    total_trades: int
    win_rate: Decimal
    avg_win_pct: Decimal
    avg_loss_pct: Decimal
    profit_factor: Decimal
    sharpe_ratio: Decimal
    max_drawdown_pct: Decimal
    final_equity: Decimal
    total_pnl_pct: Decimal
    avg_trade_duration_minutes: Decimal


@dataclass(frozen=True)
class BacktestResult:
    """Полный результат прогона."""

    trades: tuple[Trade, ...]
    equity_curve: tuple[tuple[int, Decimal], ...]   # (ts_ms, equity) после каждого fill
    summary: BacktestSummary


# Внутренняя модель — pending market order, ждёт fill следующей свечой.
@dataclass(frozen=True)
class PendingOrder:
    request: OrderRequest
    submitted_at_ms: int
    request_history_index: int  # индекс свечи на момент signal — для метрик slippage в будущем


__all__ = [
    "BacktestResult",
    "BacktestSummary",
    "FillEvent",
    "FillReason",
    "OpenPosition",
    "PendingOrder",
    "Strategy",
    "StrategyContext",
    "Trade",
]
