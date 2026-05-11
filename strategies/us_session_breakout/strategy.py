"""US session breakout стратегия.

Идея: торгуем только в US session window (13:00-15:00 UTC), вход —
пробой Asian session range (00:00-13:00 UTC). Time-of-day filter
сокращает число false signals от night/weekend шума.

См. plans/14-стратегия-us-session.md для полной spec.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from enum import StrEnum

from adapters.bingx.private_models import OrderRequest, OrderSide
from core.backtest import FillEvent, StrategyContext
from core.risk import RiskApproval, RiskEngine, RiskInputs, RiskRejection, Side
from core.signals import (
    Blacklist,
    NewsCalendar,
    SetBlacklist,
    StaticNewsCalendar,
    is_in_window,
    utc_day_of_epoch,
    utc_hour_of_day,
)
from strategies.us_session_breakout.config import UsSessionConfig

logger = logging.getLogger(__name__)

_HUNDRED = Decimal("100")


class _State(StrEnum):
    WAITING_ASIAN_START = "WAITING_ASIAN_START"
    ACCUMULATING_RANGE = "ACCUMULATING_RANGE"
    US_WINDOW = "US_WINDOW"
    POSITION_OPEN = "POSITION_OPEN"
    DAY_DONE = "DAY_DONE"


class UsSessionBreakoutStrategy:
    """Asian range breakout в US window.

    На каждом 15m close:
    - Asian window (00:00-13:00 UTC) — копим high/low.
    - US window (13:00-15:00 UTC) — ловим пробой Asian range.
    - EOD close в 23:00 UTC, если позиция ещё открыта.
    """

    def __init__(
        self,
        config: UsSessionConfig,
        risk_engine: RiskEngine,
        news_calendar: NewsCalendar | None = None,
        blacklist: Blacklist | None = None,
    ) -> None:
        self._cfg = config
        self._risk = risk_engine
        self._news = news_calendar or StaticNewsCalendar()
        self._blacklist = blacklist or SetBlacklist()

        # Per-day state. Сбрасывается на смене UTC-дня.
        self._current_day: int | None = None
        self._asian_high: Decimal | None = None
        self._asian_low: Decimal | None = None
        self._state = _State.WAITING_ASIAN_START
        self._signaled_today = False
        self._pending_coid: str | None = None

        # P&L tracking — упрощённый, как в btc_breakout.
        self._day_pnl = Decimal("0")
        self._day_trades_count = 0
        self._consecutive_losses = 0
        self._pnl_day: int | None = None

    # ── Strategy protocol ─────────────────────────────────────────────────

    def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None:
        candle = ctx.current_candle
        ts = candle.open_time_ms
        utc_day = utc_day_of_epoch(ts)
        utc_hour = utc_hour_of_day(ts)

        # Сброс state на смене UTC-дня.
        if self._current_day != utc_day:
            self._reset_day(utc_day)

        # Сброс P&L-counter'ов на смене дня (для RiskEngine).
        if self._pnl_day != utc_day:
            self._pnl_day = utc_day
            self._day_pnl = Decimal("0")
            self._day_trades_count = 0
            self._consecutive_losses = 0

        # 1. Если позиция открыта — проверяем EOD close.
        if ctx.open_position is not None:
            self._state = _State.POSITION_OPEN
            if utc_hour >= self._cfg.eod_close_hour_utc:
                # Закрываем рыночным reduce_only.
                return self._build_eod_close(ctx)
            return None

        # 2. Asian range accumulation.
        if is_in_window(
            ts, self._cfg.asian_start_hour_utc, self._cfg.asian_end_hour_utc
        ):
            self._state = _State.ACCUMULATING_RANGE
            self._asian_high = (
                candle.high
                if self._asian_high is None
                else max(self._asian_high, candle.high)
            )
            self._asian_low = (
                candle.low
                if self._asian_low is None
                else min(self._asian_low, candle.low)
            )
            return None

        # 3. US window — ловим пробой.
        if is_in_window(
            ts, self._cfg.us_start_hour_utc, self._cfg.us_end_hour_utc
        ):
            if self._state == _State.DAY_DONE or self._signaled_today:
                return None
            if self._asian_high is None or self._asian_low is None:
                # Не было полного Asian window — пропускаем день.
                self._state = _State.DAY_DONE
                return None
            return self._try_breakout(ctx)

        # 4. Вне всех окон — ничего.
        self._state = _State.DAY_DONE
        return None

    def on_fill(self, fill: FillEvent) -> None:
        if fill.reason == "ENTRY":
            self._state = _State.POSITION_OPEN
            return
        # Exit-событие.
        self._day_trades_count += 1
        if fill.reason == "STOP_LOSS":
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        self._state = _State.DAY_DONE  # один setup в день
        self._pending_coid = None

    # ── Internals ─────────────────────────────────────────────────────────

    def _reset_day(self, utc_day: int) -> None:
        self._current_day = utc_day
        self._asian_high = None
        self._asian_low = None
        self._state = _State.WAITING_ASIAN_START
        self._signaled_today = False
        self._pending_coid = None

    def _try_breakout(self, ctx: StrategyContext) -> OrderRequest | None:
        assert self._asian_high is not None
        assert self._asian_low is not None
        candle = ctx.current_candle

        midpoint = (self._asian_high + self._asian_low) / Decimal("2")
        if midpoint <= 0:
            return None
        range_pct = (
            (self._asian_high - self._asian_low) / midpoint * _HUNDRED
        )
        if range_pct < Decimal(str(self._cfg.min_range_pct)):
            self._state = _State.DAY_DONE
            return None
        if range_pct > Decimal(str(self._cfg.max_range_pct)):
            self._state = _State.DAY_DONE
            return None

        side: OrderSide
        if candle.close > self._asian_high:
            side = "BUY"
            entry = candle.close
            stop = self._asian_low
        elif candle.close < self._asian_low:
            side = "SELL"
            entry = candle.close
            stop = self._asian_high
        else:
            return None  # ждём пробоя

        # Минимальная stop_distance проверка.
        stop_distance_pct = (
            abs(entry - stop) / entry * _HUNDRED
        )
        if stop_distance_pct < Decimal(str(self._cfg.stop_min_pct)):
            return None

        # Composite фильтры.
        if self._blacklist.contains(self._cfg.symbol):
            return None
        if self._news.is_paused(candle.open_time_ms):
            return None

        # TP1.
        r_multiple = Decimal(str(self._cfg.tp1_r_multiple))
        distance = abs(entry - stop)
        tp1 = entry + r_multiple * distance if side == "BUY" else entry - r_multiple * distance

        # RiskEngine.
        risk_side = Side.LONG if side == "BUY" else Side.SHORT
        inputs = RiskInputs(
            equity=ctx.equity,
            side=risk_side,
            entry_price=entry,
            stop_price=stop,
            tier=self._cfg.risk_tier,
            day_pnl=self._day_pnl,
            day_trades_count=self._day_trades_count,
            consecutive_losses=self._consecutive_losses,
        )
        decision = self._risk.evaluate(inputs)
        if isinstance(decision, RiskRejection):
            logger.info(
                "us_session signal rejected: %s (%s)",
                decision.code,
                decision.reason,
            )
            self._state = _State.DAY_DONE
            return None

        assert isinstance(decision, RiskApproval)
        coid = uuid.uuid4().hex[:32]
        self._pending_coid = coid
        self._signaled_today = True
        self._state = _State.US_WINDOW
        return OrderRequest(
            symbol=self._cfg.symbol,
            side=side,
            order_type="MARKET",
            quantity=decision.quantity,
            attached_stop_loss=stop,
            attached_take_profit=tp1,
            client_order_id=coid,
        )

    def _build_eod_close(self, ctx: StrategyContext) -> OrderRequest | None:
        """Закрытие позиции рыночным reduce_only.

        В backtester'е стратегия не может закрыть позицию через
        on_candle_close — её закрывает либо attached SL/TP, либо
        engine при окончании данных. Поэтому здесь возвращаем None;
        фактически EOD close — это будет «end of data close» backtester'а
        (т.к. позиция переживёт несколько часов до EOD и потенциально
        SL/TP уже сработают).

        В live режиме orchestrator проверяет state стратегии и сам
        отправляет close-market. На MVP backtest полагается на end-of-data
        manual close.
        """
        return None
