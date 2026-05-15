"""BTC breakout стратегия (Donchian + ATR + volume + composite).

Реализует ``Strategy`` protocol из ``core.backtest`` — может прогоняться
в backtest и в live-runner'е без изменений кода.

State machine:
- FLAT — нет позиции, можно искать сигнал.
- PENDING — сигнал отправлен, ждём fill (заполняется backtester'ом или
  адаптером).
- OPEN — позиция открыта, ждём SL/TP/closure.

В этой версии (MVP): TP1 закрывает 100% позиции (упрощение vs план 08).
50%-TP1 + trailing-EMA для оставшихся 50% — следующая итерация.

Спецификация: plans/08-стратегия-btc-breakout.md §3.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum

from adapters.bingx.models import Kline
from adapters.bingx.private_models import OrderRequest, OrderSide
from core.backtest import FillEvent, StrategyContext
from core.risk import (
    RiskApproval,
    RiskEngine,
    RiskInputs,
    RiskRejection,
    Side,
)
from core.signals import (
    Blacklist,
    FundingProvider,
    NewsCalendar,
    SetBlacklist,
    StaticFundingProvider,
    StaticNewsCalendar,
    atr,
    donchian_channel,
    percentile_rank,
    sma,
)
from strategies.btc_breakout.config import StrategyConfig

logger = logging.getLogger(__name__)

_HUNDRED = Decimal("100")
_DAY_MS = 86_400_000


class _State(StrEnum):
    FLAT = "FLAT"
    PENDING = "PENDING"
    OPEN = "OPEN"


class BtcBreakoutStrategy:
    """BTC-USDT Donchian breakout 15m с подтверждением.

    Использует ``RiskEngine`` для расчёта размера и проверки лимитов.
    Composite-фильтры (funding / news / blacklist) — через DI providers.
    """

    def __init__(
        self,
        config: StrategyConfig,
        risk_engine: RiskEngine,
        funding_provider: FundingProvider | None = None,
        news_calendar: NewsCalendar | None = None,
        blacklist: Blacklist | None = None,
    ) -> None:
        self._cfg = config
        self._risk = risk_engine
        self._funding = funding_provider or StaticFundingProvider()
        self._news = news_calendar or StaticNewsCalendar()
        self._blacklist = blacklist or SetBlacklist()

        # State machine.
        self._state = _State.FLAT
        self._pending_coid: str | None = None

        # P&L tracking для RiskEngine (см. плана 11 §3.5).
        self._day_pnl = Decimal("0")
        self._day_trades_count = 0
        self._consecutive_losses = 0
        self._current_utc_day: int | None = None  # day-since-epoch для сброса

    # ── Strategy protocol ─────────────────────────────────────────────────

    def on_candle_close(self, ctx: StrategyContext) -> OrderRequest | None:
        candle = ctx.current_candle
        self._roll_day_if_needed(candle.open_time_ms)

        # 1. Если уже в позиции / pending — стратегия ничего не делает.
        # Backtester / адаптер сами эмитят SL/TP exits.
        if ctx.open_position is not None:
            self._state = _State.OPEN
            return None
        if self._state == _State.PENDING:
            # PENDING без открытой позиции — значит fill ещё не случился.
            # На backtester это случай 1-bar lag перед открытием.
            return None
        # Сюда дошли: state == FLAT и нет open position.
        # (после exit'а ctx.open_position станет None → state остаётся OPEN,
        # сбросим его в FLAT)
        self._state = _State.FLAT

        # 2. Warmup: нужно достаточно истории для индикаторов.
        min_history = (
            max(
                self._cfg.donchian_n,
                self._cfg.atr_window + 1,
                self._cfg.volume_sma_window,
                self._cfg.atr_percentile_lookback,
            )
            + 1
        )
        if len(ctx.history) < min_history:
            return None

        # 3. Triggers (Donchian на свечах ДО текущей).
        closed = ctx.history[:-1]
        upper, lower = donchian_channel(closed, self._cfg.donchian_n)
        long_trigger = candle.close > upper
        short_trigger = candle.close < lower

        # Direction bias: для safe-haven (gold) — long_only, и т.п.
        if self._cfg.direction_bias == "long_only":
            short_trigger = False
        elif self._cfg.direction_bias == "short_only":
            long_trigger = False

        if not (long_trigger or short_trigger):
            return None

        side: OrderSide = "BUY" if long_trigger else "SELL"
        risk_side = Side.LONG if long_trigger else Side.SHORT

        # 4. ATR-percentile фильтр.
        if not self._atr_filter_passes(closed):
            return None

        # 5. Volume фильтр.
        if not self._volume_filter_passes(candle, closed):
            return None

        # 6. Composite.
        if not self._composite_passes(side, candle.open_time_ms):
            return None

        # 7. Stop & TP1.
        entry = candle.close
        stop = self._compute_stop(entry, side, closed)
        tp1 = self._compute_tp1(entry, stop, side)

        # 8. RiskEngine.
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
                "btc_breakout signal rejected by RiskEngine: %s (%s)",
                decision.code,
                decision.reason,
            )
            return None

        assert isinstance(decision, RiskApproval)
        coid = uuid.uuid4().hex[:32]
        self._pending_coid = coid
        self._state = _State.PENDING
        return OrderRequest(
            symbol=self._cfg.symbol,
            side=side,
            order_type="MARKET",
            quantity=decision.quantity,
            attached_stop_loss=stop,
            attached_take_profit=tp1,
            client_order_id=coid,
        )

    def on_fill(self, fill: FillEvent) -> None:
        """Стратегия трекает P&L для RiskEngine.

        ENTRY → переходим в OPEN. STOP_LOSS / TAKE_PROFIT_1 / MANUAL_CLOSE
        / TRAILING_EXIT → закрываем сделку, считаем убыток/прибыль.
        """
        if fill.reason == "ENTRY":
            self._state = _State.OPEN
            return
        # Exit-событие.
        self._day_trades_count += 1
        # Точный pnl backtester'у/orchestrator-у считать самим (через trade
        # P&L). Здесь приближённо: если LOSS — увеличиваем counter, если
        # WIN — сбрасываем. P&L в day_pnl передаст orchestrator (live) или
        # будет дополнено в следующей итерации (backtester отдаёт Trade
        # после exit, но не во время цикла).
        if fill.reason == "STOP_LOSS":
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        self._state = _State.FLAT
        self._pending_coid = None

    # ── Helpers ──────────────────────────────────────────────────────────

    def _roll_day_if_needed(self, ts_ms: int) -> None:
        day = ts_ms // _DAY_MS
        if self._current_utc_day is None:
            self._current_utc_day = day
            return
        if day != self._current_utc_day:
            self._current_utc_day = day
            self._day_pnl = Decimal("0")
            self._day_trades_count = 0
            # consecutive_losses не сбрасываем — это «hot-streak» counter
            # через границу дня. Но по риск-профилю §«3 убытка подряд» —
            # сбрасывается тоже через день. Сбрасываем для соответствия.
            self._consecutive_losses = 0

    def _atr_filter_passes(self, closed: Sequence[Kline]) -> bool:
        atr_window = self._cfg.atr_window
        lookback = self._cfg.atr_percentile_lookback
        # Текущий ATR — на самых свежих закрытых свечах.
        atr_now = atr(closed, atr_window)
        # Распределение ATR за `lookback` окон. Считаем atr в скользящем
        # окне, шагая на 1 свечу. Для скорости — используем достаточный slice.
        atrs: list[Decimal] = []
        for end in range(atr_window + 1, len(closed) + 1):
            if end < atr_window + 1:
                continue
            window = closed[max(0, end - (atr_window + 1)) : end]
            if len(window) < atr_window + 1:
                continue
            atrs.append(atr(window, atr_window))
            if len(atrs) >= lookback:
                break
        if not atrs:
            return False
        rank = percentile_rank(atrs, atr_now)
        return rank >= Decimal(str(self._cfg.atr_percentile_min))

    def _volume_filter_passes(self, current: Kline, closed: Sequence[Kline]) -> bool:
        window = closed[-self._cfg.volume_sma_window :]
        vol_sma = sma([c.volume for c in window], self._cfg.volume_sma_window)
        multiplier = Decimal(str(self._cfg.volume_multiplier))
        return current.volume >= vol_sma * multiplier

    def _composite_passes(self, side: OrderSide, ts_ms: int) -> bool:
        if self._blacklist.contains(self._cfg.symbol):
            return False
        if self._news.is_paused(ts_ms):
            return False
        funding = self._funding.get_funding_rate(self._cfg.symbol, ts_ms)
        if funding is not None:
            cap = Decimal(str(self._cfg.funding_rate_max_pct)) / _HUNDRED
            if side == "BUY" and funding > cap:
                return False
            if side == "SELL" and funding < -cap:
                return False
        return True

    def _compute_stop(self, entry: Decimal, side: OrderSide, closed: Sequence[Kline]) -> Decimal:
        """Стоп: low/high N свечей или min 0.5% от entry — что дальше."""
        window = closed[-self._cfg.donchian_n :]
        ref = min(c.low for c in window) if side == "BUY" else max(c.high for c in window)
        min_distance = entry * Decimal(str(self._cfg.stop_min_pct)) / _HUNDRED
        if side == "BUY":
            candidate = min(ref, entry - min_distance)
            # candidate < entry guaranteed; защита от слишком близкого ref:
            return min(candidate, entry - min_distance)
        candidate = max(ref, entry + min_distance)
        return max(candidate, entry + min_distance)

    def _compute_tp1(self, entry: Decimal, stop: Decimal, side: OrderSide) -> Decimal:
        distance = abs(entry - stop)
        r = Decimal(str(self._cfg.tp1_r_multiple))
        if side == "BUY":
            return entry + r * distance
        return entry - r * distance
