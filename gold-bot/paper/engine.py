"""PaperEngine: применяет стратегию к закрытым свечам, симулирует fills,
ведёт состояние и пишет в журнал.

Контракт fill совпадает с `backtest.engine.BacktestEngine`:
- сигнал на свече N → MARKET-fill по open свечи N+1;
- стоп/тейк проверяются внутри той же свечи N+1 по high/low; если оба
  задеты — консервативно стоп.

Кроме fill-контракта дополнительно поднимаем circuit breakers RiskState:
kill-switch (−15% от пика эквити), дневной стоп, серия убытков. Это
именно то, что paper должен подтвердить на живых данных.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from backtest.costs import CostModel
from backtest.strategy import Signal, Strategy
from exchanges.models import OHLCV, OrderSide
from paper.journal import OpenPositionRecord, PaperJournal, TradeRecord
from risk.config import RiskConfig
from risk.engine import RiskState, compute_sizing


@dataclass(frozen=True)
class EngineSnapshot:
    """Что движок вернул после обработки одной свечи — для логов и тестов."""

    closed_trade: TradeRecord | None
    opened_position: OpenPositionRecord | None
    rejected_reason: str | None
    equity: Decimal


def _exit_level(candle: OHLCV, pos: OpenPositionRecord) -> tuple[Decimal, str] | None:
    """Сработал ли стоп/тейк внутри бара. Консервативно: при обоих — стоп."""
    if pos.side is OrderSide.BUY:
        if candle.low <= pos.stop:
            return pos.stop, "stop"
        if candle.high >= pos.take_profit:
            return pos.take_profit, "tp"
    else:
        if candle.high >= pos.stop:
            return pos.stop, "stop"
        if candle.low <= pos.take_profit:
            return pos.take_profit, "tp"
    return None


class PaperEngine:
    def __init__(
        self,
        symbol: str,
        strategy: Strategy,
        cost_model: CostModel,
        risk_cfg: RiskConfig,
        journal: PaperJournal,
        starting_equity: Decimal,
    ) -> None:
        self._symbol = symbol
        self._strategy = strategy
        self._costs = cost_model
        self._cfg = risk_cfg
        self._journal = journal
        self._equity: Decimal = journal.get_equity() or starting_equity
        if journal.get_equity() is None:
            journal.set_equity(self._equity)
        # история закрытых свечей по этому символу: накапливаем в памяти,
        # стратегия видит history[:i+1]. На рестарте подтягиваем последние
        # N свечей у caller'а (runner делает это перед циклом).
        self._history: list[OHLCV] = []
        # сигнал предыдущей закрытой свечи — будет исполнен по open ЭТОЙ свечи.
        self._pending_signal_ts: int | None = None
        self._pending_signal: Signal | None = None
        self._risk_state = RiskState.new(starting_equity, _utc_today())

    @property
    def equity(self) -> Decimal:
        return self._equity

    @property
    def risk_state(self) -> RiskState:
        return self._risk_state

    def seed_history(self, candles: list[OHLCV]) -> None:
        """Заполнить историю на старте (закрытые свечи до текущего момента)."""
        self._history = list(candles)

    def process_closed_candle(self, candle: OHLCV) -> EngineSnapshot:
        """Один цикл: закрытие позиции, исполнение pending, поиск нового сигнала.

        Возвращает snapshot для логов. Все изменения состояния — внутри
        одной SQLite-транзакции; на крах посередине состояние не разъедется.
        """
        self._risk_state.roll_period(_utc_today())
        closed_trade: TradeRecord | None = None
        opened_position: OpenPositionRecord | None = None
        rejected_reason: str | None = None

        with self._journal.transaction():
            open_pos = self._journal.get_open_position(self._symbol)

            # 1) если позиция открыта — проверить exit на этой свече
            if open_pos is not None:
                exit_hit = _exit_level(candle, open_pos)
                if exit_hit is not None:
                    exit_price, reason = exit_hit
                    closed_trade = self._close_position(
                        open_pos, candle.timestamp, exit_price, reason
                    )

            # 2) если позиция теперь закрыта и есть pending — открыть по open
            if (
                self._journal.get_open_position(self._symbol) is None
                and self._pending_signal is not None
            ):
                opened_position = self._try_open(candle)
                if opened_position is None:
                    rejected_reason = "risk_rejected"
                self._pending_signal = None
                self._pending_signal_ts = None

            # 3) если позиции нет и pending нет — спросить стратегию по истории
            self._history.append(candle)
            if (
                self._journal.get_open_position(self._symbol) is None
                and self._pending_signal is None
                and not self._risk_state.killed
                and self._risk_state.day not in self._risk_state.halted_days
            ):
                signal = self._strategy.on_candle(self._history)
                if signal is not None:
                    self._pending_signal = signal
                    self._pending_signal_ts = candle.timestamp

            self._journal.set_last_candle_ts(self._symbol, candle.timestamp)

        return EngineSnapshot(
            closed_trade=closed_trade,
            opened_position=opened_position,
            rejected_reason=rejected_reason,
            equity=self._equity,
        )

    def _try_open(self, candle: OHLCV) -> OpenPositionRecord | None:
        signal = self._pending_signal
        assert signal is not None  # вызывается только когда pending есть
        entry = candle.open
        decision = compute_sizing(
            self._cfg, self._equity, entry, signal.stop, signal.side, signal.risk_pct
        )
        if not decision.approved or decision.sizing is None:
            return None
        qty = decision.sizing.quantity
        entry_cost = self._costs.leg_cost(qty * entry)
        pos = OpenPositionRecord(
            symbol=self._symbol,
            side=signal.side,
            entry_ts=candle.timestamp,
            entry_price=entry,
            quantity=qty,
            stop=signal.stop,
            take_profit=signal.take_profit,
            entry_cost=entry_cost,
        )
        self._journal.set_open_position(pos)
        return pos

    def _close_position(
        self, pos: OpenPositionRecord, exit_ts: int, exit_price: Decimal, reason: str
    ) -> TradeRecord:
        direction = Decimal(1) if pos.side is OrderSide.BUY else Decimal(-1)
        gross = (exit_price - pos.entry_price) * pos.quantity * direction
        exit_cost = self._costs.leg_cost(pos.quantity * exit_price)
        total_costs = pos.entry_cost + exit_cost
        net = gross - total_costs
        new_equity = self._equity + net
        trade = TradeRecord(
            symbol=self._symbol,
            side=pos.side,
            entry_ts=pos.entry_ts,
            exit_ts=exit_ts,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            quantity=pos.quantity,
            gross_pnl=gross,
            costs=total_costs,
            net_pnl=net,
            exit_reason=reason,
            equity_after=new_equity,
        )
        self._equity = new_equity
        self._journal.delete_open_position(pos.symbol)
        self._journal.append_trade(trade)
        self._journal.append_equity_point(exit_ts, new_equity)
        self._journal.set_equity(new_equity)
        # circuit breakers
        self._risk_state.day_pnl += net
        self._risk_state.week_pnl += net
        self._risk_state.month_pnl += net
        self._risk_state.consecutive_losses = (
            self._risk_state.consecutive_losses + 1 if net < 0 else 0
        )
        self._risk_state.update_equity(new_equity, self._cfg)
        cap = self._risk_state.active_capital
        if cap > 0 and (
            self._risk_state.day_pnl / cap <= self._cfg.daily_stop_pct
            or self._risk_state.consecutive_losses >= self._cfg.max_consecutive_losses
        ):
            self._risk_state.halted_days.add(self._risk_state.day)
        return trade


def _utc_today() -> date:
    return datetime.now(tz=UTC).date()
