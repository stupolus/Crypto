"""ExitTracker — связь между entry-сделкой (trade_id) и её exit-fill (SL/TP).

Цель: автоматически вызывать ``TradeOutcomeLogger.record_exit`` когда биржа
fillит attached SL или TP. Это последний кирпич Layer 6 (plan #18) — без
него сделки в БД остаются "открытыми" навсегда.

Сейчас single-symbol mode: одна позиция на символ. Если runner будет
вести 2+ концурентных позиций на одном symbol — нужно расширение.
Большинство стратегий из plan'ов работают one-at-a-time, поэтому MVP.

Public API:
- ``register_entry(trade_id, symbol, entry_price, size, entry_time_ms)``:
  фиксируем что на символе теперь open сделка.
- ``observe_order_event(event) → ExitData | None``: если event — закрытие,
  возвращаем ExitData готовый для record_exit. Иначе None.
- ``close_unfilled(trade_id)``: если сделка отменена (cancel, expired) —
  убираем из памяти.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from adapters.bingx.private_models import OrderUpdateEvent
from core.postmortem.models import ExitData, ExitReason

logger = logging.getLogger(__name__)

# Типы ордеров, fill которых = закрытие позиции (attached SL/TP).
_EXIT_ORDER_TYPES = {
    "STOP_MARKET",
    "STOP",
    "TAKE_PROFIT_MARKET",
    "TAKE_PROFIT",
}


@dataclass(frozen=True)
class _OpenTrade:
    trade_id: str
    symbol: str
    entry_price: Decimal
    size: Decimal
    entry_time_ms: int


class ExitTracker:
    """Сопоставляет fill-события закрытия с открытыми trade_id.

    Использование::

        tracker = ExitTracker()
        tracker.register_entry(trade_id, symbol, entry_price, size, entry_time_ms)
        # ... позже из user-stream:
        exit_data = tracker.observe_order_event(order_update)
        if exit_data:
            logger.record_exit(trade_id, exit_data)
    """

    def __init__(self) -> None:
        # symbol → _OpenTrade. Одна позиция на символ (MVP).
        self._open: dict[str, _OpenTrade] = {}

    def register_entry(
        self,
        *,
        trade_id: str,
        symbol: str,
        entry_price: Decimal,
        size: Decimal,
        entry_time_ms: int,
    ) -> None:
        """Фиксируем открытие сделки.

        Если на символе уже была open сделка — она overwrite'нется
        (предыдущая закрытая нами не была — runner не fillил её exit?).
        Это сигнал тревоги: возможно потеряли OrderUpdateEvent или
        концурентная позиция (не поддерживается MVP).
        """
        if symbol in self._open:
            logger.warning(
                "ExitTracker: overwriting open trade for %s (%s → %s) — возможно потерян exit fill",
                symbol,
                self._open[symbol].trade_id,
                trade_id,
            )
        self._open[symbol] = _OpenTrade(
            trade_id=trade_id,
            symbol=symbol,
            entry_price=entry_price,
            size=size,
            entry_time_ms=entry_time_ms,
        )
        logger.info("ExitTracker: registered open %s on %s @ %s", trade_id, symbol, entry_price)

    def observe_order_event(self, event: OrderUpdateEvent) -> tuple[str, ExitData] | None:
        """Обработать OrderUpdateEvent. Возвращает (trade_id, ExitData) если
        это закрытие нашей позиции, иначе None.

        Detection rules:
        - status == FILLED
        - type in {STOP_*, TAKE_PROFIT_*}
        - symbol присутствует в нашей памяти open trades
        - executed_quantity > 0

        Если detected — удаляем из памяти (closed) и возвращаем ExitData.
        """
        if event.status != "FILLED":
            return None
        if event.type not in _EXIT_ORDER_TYPES:
            return None
        open_trade = self._open.get(event.symbol)
        if open_trade is None:
            logger.debug(
                "ExitTracker: %s close fill on %s — но нет нашей open сделки, skip",
                event.type,
                event.symbol,
            )
            return None
        if event.executed_quantity <= Decimal("0"):
            return None

        exit_price = event.average_price or event.price
        if exit_price <= Decimal("0"):
            logger.warning("ExitTracker: zero exit_price для %s", event.symbol)
            return None

        exit_reason = _infer_exit_reason(event.type)
        pnl_usd = event.realised_profit if event.realised_profit is not None else Decimal("0")
        pnl_pct = _compute_pnl_pct(open_trade.entry_price, exit_price, open_trade.size)
        holding_time_min = max(0, (event.event_time_ms - open_trade.entry_time_ms) // 60_000)

        exit_data = ExitData(
            exit_time_ms=event.event_time_ms,
            exit_price=exit_price,
            pnl_usd=pnl_usd,
            pnl_pct=pnl_pct,
            exit_reason=exit_reason,
            holding_time_min=holding_time_min,
        )

        del self._open[event.symbol]
        logger.info(
            "ExitTracker: closed %s on %s @ %s | reason=%s PnL%%=%s",
            open_trade.trade_id,
            event.symbol,
            exit_price,
            exit_reason,
            pnl_pct,
        )
        return open_trade.trade_id, exit_data

    def close_unfilled(self, symbol: str) -> str | None:
        """Удалить open сделку без записи ExitData (cancel / manual close).

        Возвращает trade_id если что-то было удалено.
        """
        trade = self._open.pop(symbol, None)
        if trade is not None:
            logger.info("ExitTracker: dropped open trade %s on %s", trade.trade_id, symbol)
            return trade.trade_id
        return None

    @property
    def open_count(self) -> int:
        return len(self._open)

    def has_open(self, symbol: str) -> bool:
        return symbol in self._open


def _infer_exit_reason(order_type: str) -> ExitReason:
    """Маппинг BingX OrderType → ExitReason."""
    if order_type.startswith("STOP"):
        return "SL"
    if order_type.startswith("TAKE_PROFIT"):
        return "TP1"
    # Не должно сюда попасть (мы filter'уем в _EXIT_ORDER_TYPES), но safe-fallback.
    return "MANUAL"


def _compute_pnl_pct(entry_price: Decimal, exit_price: Decimal, size: Decimal) -> Decimal:
    """PnL % от notional entry_value.

    long: (exit - entry) / entry × 100
    short: (entry - exit) / entry × 100 — но size знаковая, поэтому
    общая формула: (exit - entry) / entry × sign(size) × 100.

    Здесь мы используем raw entry_price, не считаем сторону — runner
    при register_entry передаёт |size|, направление в trade_id.
    Упрощение: возвращаем (exit - entry) / entry × 100 как для long.
    Точное PnL вычисляется ExitTracker через realised_profit от биржи.
    """
    if entry_price <= Decimal("0"):
        return Decimal("0")
    _ = size  # пока не используется в этой формуле
    return ((exit_price - entry_price) / entry_price * Decimal("100")).quantize(Decimal("0.001"))
