"""Event-driven backtester.

Прогоняет ``Strategy`` по последовательности ``Kline`` свечей. На каждой
закрытой свече стратегия может вернуть `OrderRequest` — backtester
эмулирует fill **следующей** свечой по `open + slippage` (lag prevents
lookahead bias). Attached SL/TP проверяются на high/low каждой свечи
**с открытой позицией**.

Принципиально: индикаторы стратегия считает на ``ctx.history`` (which
includes ``current_candle``). Видеть ``c+1`` и далее запрещено — это
проверяется unit-тестом «перемешивание будущих свечей не меняет результат».
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from adapters.bingx.models import Kline
from adapters.bingx.private_models import OrderRequest, OrderSide
from core.backtest.config import BacktestConfig, get_default_config
from core.backtest.metrics import compute_summary
from core.backtest.models import (
    BacktestResult,
    FillEvent,
    FillReason,
    OpenPosition,
    PendingOrder,
    Strategy,
    StrategyContext,
    Trade,
)

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_BPS_DENOMINATOR = Decimal("10000")


class _TradeBuilder:
    """Накопитель fills одной сделки + MFE/MAE per trade."""

    def __init__(self, entry: FillEvent, side_sign: Decimal) -> None:
        self.entry = entry
        self.side_sign = side_sign  # +1 LONG, -1 SHORT
        self.exits: list[FillEvent] = []
        self.mfe_pct = _ZERO
        self.mae_pct = _ZERO

    def update_excursion(self, high: Decimal, low: Decimal) -> None:
        """Обновить MFE/MAE по диапазону свечи."""
        if self.side_sign > 0:  # LONG
            up = (high - self.entry.price) / self.entry.price * _HUNDRED
            down = (low - self.entry.price) / self.entry.price * _HUNDRED
        else:  # SHORT
            up = (self.entry.price - low) / self.entry.price * _HUNDRED
            down = (self.entry.price - high) / self.entry.price * _HUNDRED
        if up > self.mfe_pct:
            self.mfe_pct = up
        if down < self.mae_pct:
            self.mae_pct = down

    def finalize(self) -> Trade:
        entry_notional = self.entry.price * self.entry.quantity
        # P&L = side_sign × Σ((exit_price − entry_price) × exit_qty) − fees.
        pnl = -self.entry.fee
        for ex in self.exits:
            pnl += self.side_sign * (ex.price - self.entry.price) * ex.quantity
            pnl -= ex.fee
        pnl_pct = pnl / entry_notional * _HUNDRED if entry_notional > 0 else _ZERO
        duration_ms = self.exits[-1].timestamp_ms - self.entry.timestamp_ms if self.exits else 0
        return Trade(
            entry=self.entry,
            exits=tuple(self.exits),
            pnl=pnl,
            pnl_pct=pnl_pct,
            duration_ms=duration_ms,
            max_favorable_excursion_pct=self.mfe_pct,
            max_adverse_excursion_pct=self.mae_pct,
        )


class BacktestEngine:
    """Event-driven прогон стратегии."""

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self._config = config or get_default_config()

    @property
    def config(self) -> BacktestConfig:
        return self._config

    def run(
        self,
        strategy: Strategy,
        candles: Sequence[Kline],
    ) -> BacktestResult:
        if not candles:
            return BacktestResult(
                trades=(),
                equity_curve=(),
                summary=compute_summary([], [], self._config.initial_equity_decimal),
            )

        equity = self._config.initial_equity_decimal
        history: list[Kline] = []
        pending: PendingOrder | None = None
        open_pos: OpenPosition | None = None
        builder: _TradeBuilder | None = None

        trades: list[Trade] = []
        equity_curve: list[tuple[int, Decimal]] = []

        for idx, candle in enumerate(candles):
            # 1. Если есть pending market order — fill по open текущей свечи.
            if pending is not None and open_pos is None:
                fill = self._simulate_market_fill(
                    request=pending.request,
                    fill_price=candle.open,
                    fill_time_ms=candle.open_time_ms,
                    reason="ENTRY",
                )
                equity -= fill.fee
                equity_curve.append((fill.timestamp_ms, equity))
                strategy.on_fill(fill)

                open_pos = self._open_position_from_request(pending.request, fill)
                builder = _TradeBuilder(
                    entry=fill,
                    side_sign=Decimal("1") if pending.request.side == "BUY" else Decimal("-1"),
                )
                pending = None

            # 2. Если позиция открыта — проверяем SL/TP на диапазоне свечи.
            if open_pos is not None and builder is not None:
                builder.update_excursion(candle.high, candle.low)
                exit_fill = self._check_attached_exits(open_pos, candle)
                if exit_fill is not None:
                    equity += (
                        builder.side_sign
                        * (exit_fill.price - open_pos.entry_price)
                        * exit_fill.quantity
                    )
                    equity -= exit_fill.fee
                    equity_curve.append((exit_fill.timestamp_ms, equity))
                    strategy.on_fill(exit_fill)
                    builder.exits.append(exit_fill)
                    trades.append(builder.finalize())
                    open_pos = None
                    builder = None

            # 3. Закрытие свечи — стратегия получает контекст.
            history.append(candle)
            ctx = StrategyContext(
                current_candle=candle,
                history=tuple(history),  # immutable view
                equity=equity,
                open_position=open_pos,
            )
            signal = strategy.on_candle_close(ctx)

            # 4. Если signal — записываем как pending (fill на следующей свече).
            if signal is not None and open_pos is None and pending is None:
                pending = PendingOrder(
                    request=signal,
                    submitted_at_ms=candle.open_time_ms,
                    request_history_index=idx,
                )

        # В конце теста — closing open position по close последней свечи.
        if open_pos is not None and builder is not None:
            last_candle = candles[-1]
            close_fill = self._simulate_close_fill(
                position=open_pos,
                price=last_candle.close,
                time_ms=last_candle.open_time_ms,
                reason="MANUAL_CLOSE",
            )
            equity += (
                builder.side_sign * (close_fill.price - open_pos.entry_price) * close_fill.quantity
            )
            equity -= close_fill.fee
            equity_curve.append((close_fill.timestamp_ms, equity))
            builder.exits.append(close_fill)
            trades.append(builder.finalize())

        summary = compute_summary(trades, equity_curve, self._config.initial_equity_decimal)
        return BacktestResult(
            trades=tuple(trades),
            equity_curve=tuple(equity_curve),
            summary=summary,
        )

    # ── Симуляция fills ──────────────────────────────────────────────────

    def _simulate_market_fill(
        self,
        *,
        request: OrderRequest,
        fill_price: Decimal,
        fill_time_ms: int,
        reason: FillReason,
    ) -> FillEvent:
        slippage_factor = Decimal(str(self._config.slippage_bps)) / _BPS_DENOMINATOR
        # Slippage всегда против нас: BUY дороже, SELL дешевле.
        if request.side == "BUY":
            adjusted_price = fill_price * (Decimal("1") + slippage_factor)
        else:
            adjusted_price = fill_price * (Decimal("1") - slippage_factor)
        notional = adjusted_price * request.quantity
        fee = notional * Decimal(str(self._config.fees.taker_pct)) / _HUNDRED
        return FillEvent(
            timestamp_ms=fill_time_ms,
            side=request.side,
            price=adjusted_price,
            quantity=request.quantity,
            fee=fee,
            reason=reason,
        )

    def _simulate_close_fill(
        self,
        *,
        position: OpenPosition,
        price: Decimal,
        time_ms: int,
        reason: FillReason,
    ) -> FillEvent:
        """Закрытие по market без slippage adjustment — для SL/TP exit
        slippage уже учтён через цену касания. Для manual_close при
        окончании теста — берём close без adjustment (известная цена).
        """
        close_side: OrderSide = "SELL" if position.side == "BUY" else "BUY"
        notional = price * abs(position.quantity)
        fee = notional * Decimal(str(self._config.fees.taker_pct)) / _HUNDRED
        return FillEvent(
            timestamp_ms=time_ms,
            side=close_side,
            price=price,
            quantity=abs(position.quantity),
            fee=fee,
            reason=reason,
        )

    def _check_attached_exits(self, position: OpenPosition, candle: Kline) -> FillEvent | None:
        """Проверить SL/TP на high/low свечи.

        Приоритет SL над TP при касании обоих в одной свече (worst case).
        Возвращает один FillEvent или None.
        """
        is_long = position.side == "BUY"
        # Stop loss
        sl_hit = (is_long and candle.low <= position.stop_price) or (
            not is_long and candle.high >= position.stop_price
        )
        # Take profit (опц.)
        tp_hit = position.take_profit_price is not None and (
            (is_long and candle.high >= position.take_profit_price)
            or (not is_long and candle.low <= position.take_profit_price)
        )
        if sl_hit:
            return self._simulate_close_fill(
                position=position,
                price=position.stop_price,
                time_ms=candle.open_time_ms,
                reason="STOP_LOSS",
            )
        if tp_hit:
            assert position.take_profit_price is not None
            return self._simulate_close_fill(
                position=position,
                price=position.take_profit_price,
                time_ms=candle.open_time_ms,
                reason="TAKE_PROFIT_1",
            )
        return None

    @staticmethod
    def _open_position_from_request(request: OrderRequest, fill: FillEvent) -> OpenPosition:
        assert request.attached_stop_loss is not None, (
            "OrderRequest invariant: entry must have attached_stop_loss"
        )
        # Размер хранится со знаком: + LONG, - SHORT.
        signed_qty = fill.quantity if request.side == "BUY" else -fill.quantity
        return OpenPosition(
            entry_price=fill.price,
            quantity=signed_qty,
            side=request.side,
            stop_price=request.attached_stop_loss,
            take_profit_price=request.attached_take_profit,
            entry_time_ms=fill.timestamp_ms,
        )
