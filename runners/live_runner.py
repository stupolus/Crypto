"""Live-runner: соединяет BingX-адаптер + стратегию + journal в один процесс.

Минимальный orchestrator, который:
1. Подписывается на свечи через ``BingXMarketWebSocket``.
2. На каждой закрытой свече вызывает ``strategy.on_candle_close``.
3. Если стратегия вернула ``OrderRequest`` — отправляет через ``PrivateAPI.place_order``.
4. Параллельно подписан на ``BingXUserDataStream`` — push-события fill'ов
   передаются в ``strategy.on_fill``.
5. Все события + журнал + метрики пишутся через адаптерные `OrderJournal`
   / `MetricsWriter`.

Использование:
    .venv/bin/python -m runners.live_runner \\
        --strategy btc_breakout \\
        --symbol BTC-USDT \\
        --interval 15m

**Запускать только на VST** до явного решения по live. Проверяется
переменной `BINGX_ENV` в `.env`.

Что НЕ делает этот runner (отложено):
- Не делает initial state restore из journal (если процесс упал во время
  открытой позиции — нужно вручную проверить через `api.get_positions`
  перед перезапуском).
- Не интегрирует RiskEngine на уровне runner'а — стратегия сама зовёт его.
- Не делает graceful drain на сигнал SIGTERM (используется только KeyboardInterrupt).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from adapters.bingx.client import BingXClient
from adapters.bingx.journal import OrderJournal
from adapters.bingx.metrics import MetricsWriter
from adapters.bingx.models import Kline
from adapters.bingx.private import PrivateAPI
from adapters.bingx.private_models import (
    OrderUpdateEvent,
    UserStreamEvent,
)
from adapters.bingx.public import PublicAPI
from adapters.bingx.settings import BingXSettings
from adapters.bingx.user_stream import BingXUserDataStream
from adapters.bingx.websocket import BingXMarketWebSocket
from core.backtest.models import OpenPosition, StrategyContext
from core.risk import RiskEngine
from strategies.btc_breakout import BtcBreakoutStrategy, get_default_config
from strategies.trend_ema_4h import (
    TrendEmaStrategy,
)
from strategies.trend_ema_4h import (
    get_default_config as trend_get_default_config,
)
from strategies.us_session_breakout import (
    UsSessionBreakoutStrategy,
)
from strategies.us_session_breakout import (
    get_default_config as us_get_default_config,
)

logger = logging.getLogger(__name__)


@dataclass
class RunnerState:
    """Минимальный state runner'а — в памяти.

    Persistence — OrderJournal (для ордеров) + BingX-side (для позиций).
    Поэтому хранить много здесь не нужно.
    """

    candles_history: list[Kline]
    open_position: OpenPosition | None = None
    equity: Decimal = Decimal("0")


def _interval_to_ms(interval: str) -> int:
    table = {
        "1m": 60_000,
        "3m": 180_000,
        "5m": 300_000,
        "15m": 900_000,
        "30m": 1_800_000,
        "1h": 3_600_000,
        "2h": 7_200_000,
        "4h": 14_400_000,
        "6h": 21_600_000,
        "8h": 28_800_000,
        "12h": 43_200_000,
        "1d": 86_400_000,
    }
    if interval not in table:
        raise SystemExit(f"unsupported interval: {interval}")
    return table[interval]


def _build_strategy(name: str, risk_engine: RiskEngine) -> Any:
    if name == "btc_breakout":
        return BtcBreakoutStrategy(config=get_default_config(), risk_engine=risk_engine)
    if name == "us_session_breakout":
        return UsSessionBreakoutStrategy(
            config=us_get_default_config(), risk_engine=risk_engine
        )
    if name == "trend_ema_4h":
        return TrendEmaStrategy(
            config=trend_get_default_config(), risk_engine=risk_engine
        )
    raise SystemExit(f"unknown strategy: {name}")


def _decode_kline_message(payload: dict[str, Any]) -> Kline | None:
    """Из WS-сообщения kline вытащить закрытую свечу.

    BingX market WS kline payload: ``{"data": [{"T": close_time, "t": open_time,
    "o", "c", "h", "l", "v", "x": is_closed, ...}]}``.

    Возвращаем None если свеча ещё не закрылась.
    """
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        return None
    candle = data[0]
    if not candle.get("x", False):  # not closed yet
        return None
    return Kline.model_validate(
        {
            "time": int(candle["t"]),
            "open": str(candle["o"]),
            "high": str(candle["h"]),
            "low": str(candle["l"]),
            "close": str(candle["c"]),
            "volume": str(candle.get("v", "0")),
        }
    )


async def _warm_history(
    public_api: PublicAPI, symbol: str, interval: str, count: int
) -> list[Kline]:
    """Подтянуть последние N свечей через REST до старта WS-подписки."""
    candles = await public_api.get_klines(
        symbol=symbol, interval=interval, limit=count
    )
    logger.info(
        "warmed history: %d candles for %s %s", len(candles), symbol, interval
    )
    return candles


async def _fetch_equity(private_api: PrivateAPI) -> Decimal:
    """Equity для RiskEngine = `balance` основного актива (VST/USDT)."""
    balances = await private_api.get_balance()
    if not balances:
        return Decimal("0")
    # Берём VST если есть (demo), иначе USDT.
    for asset in ("VST", "USDT"):
        for b in balances:
            if b.asset == asset:
                return b.equity
    return balances[0].equity


async def run(args: argparse.Namespace) -> None:
    settings = BingXSettings()
    if settings.env == "live":
        raise SystemExit(
            "Refusing to run on live without --i-know-what-im-doing. "
            "Set BINGX_ENV=vst in .env."
        )
    journal_path = Path(args.journal_db)
    metrics_path = Path(args.metrics_file)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)

    journal = OrderJournal(journal_path)
    metrics = MetricsWriter(metrics_path)

    risk = RiskEngine()
    strategy = _build_strategy(args.strategy, risk)
    logger.info("strategy initialized: %s", args.strategy)

    async with BingXClient(settings=settings) as client:
        public_api = PublicAPI(client, client.config)
        private_api = PrivateAPI(client, journal=journal, metrics=metrics)

        history = await _warm_history(
            public_api, args.symbol, args.interval, count=args.warmup_candles
        )
        equity = await _fetch_equity(private_api)
        logger.info("starting equity: %s", equity)

        state = RunnerState(candles_history=history, equity=equity)

        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)

        async with BingXUserDataStream(private_api) as user_stream:
            user_task = asyncio.create_task(
                _user_events_loop(user_stream, strategy, state, journal),
                name="live-user-stream",
            )

            try:
                await _candle_loop(
                    args=args,
                    strategy=strategy,
                    state=state,
                    private_api=private_api,
                    stop_event=stop_event,
                )
            finally:
                stop_event.set()
                user_task.cancel()
                with suppress(asyncio.CancelledError):
                    await user_task

    logger.info("live runner stopped cleanly")


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):  # Windows
            loop.add_signal_handler(sig, stop_event.set)


async def _user_events_loop(
    stream: BingXUserDataStream,
    strategy: Any,
    state: RunnerState,
    journal: OrderJournal,
) -> None:
    """Прокидывает события из user-stream в стратегию + обновляет state."""
    async for event in stream.events():
        try:
            await _handle_user_event(event, strategy, state, journal)
        except Exception:
            logger.exception("user event handler error for %r", event)


async def _handle_user_event(
    event: UserStreamEvent,
    strategy: Any,
    state: RunnerState,
    journal: OrderJournal,
) -> None:
    from adapters.bingx.private_models import AccountUpdateEvent

    if isinstance(event, OrderUpdateEvent):
        # Передаём в стратегию для P&L tracking.
        from core.backtest.models import FillEvent

        if event.execution_type == "TRADE":
            # synthetic FillEvent для стратегии (стратегия ждёт FillEvent).
            avg = event.average_price or Decimal("0")
            fill = FillEvent(
                timestamp_ms=event.event_time_ms,
                side=event.side,
                price=avg,
                quantity=event.executed_quantity,
                fee=Decimal("0"),  # реальный fee BingX в commission поле, опционально
                reason="ENTRY" if state.open_position is None else "STOP_LOSS",
            )
            try:
                strategy.on_fill(fill)
            except Exception:
                logger.exception("strategy.on_fill failed")
        # Обновляем journal.
        try:
            await journal.update_from_event(event)
        except Exception:
            logger.exception("journal update_from_event failed")
        return
    if isinstance(event, AccountUpdateEvent):
        # Обновляем equity из push (быстрее REST poll).
        for delta in event.balances:
            if delta.asset in ("VST", "USDT"):
                state.equity = delta.wallet_balance
                logger.debug("equity updated: %s", state.equity)
        # Открытые позиции (упрощённо).
        if event.positions:
            state.open_position = _build_open_position(event.positions[0])
        else:
            state.open_position = None
        return
    # RECONCILE event — пересоздаём state.
    from adapters.bingx.private_models import UserStreamReconcileEvent

    if isinstance(event, UserStreamReconcileEvent):
        if event.positions:
            non_zero = [p for p in event.positions if p.position_amount != 0]
            if non_zero:
                state.open_position = _build_open_position_from_position(non_zero[0])
        for b in event.balances:
            if b.asset in ("VST", "USDT"):
                state.equity = b.equity
        logger.info(
            "reconcile: equity=%s open=%s",
            state.equity,
            state.open_position is not None,
        )


def _build_open_position(delta: Any) -> OpenPosition | None:
    if delta.position_amount == 0:
        return None
    from adapters.bingx.private_models import OrderSide

    side: OrderSide = "BUY" if delta.position_amount > 0 else "SELL"
    return OpenPosition(
        entry_price=delta.entry_price,
        quantity=delta.position_amount,
        side=side,
        stop_price=Decimal("0"),  # неизвестно из ACCOUNT_UPDATE
        take_profit_price=None,
        entry_time_ms=0,
    )


def _build_open_position_from_position(pos: Any) -> OpenPosition | None:
    if pos.position_amount == 0:
        return None
    from adapters.bingx.private_models import OrderSide

    side: OrderSide = "BUY" if pos.position_amount > 0 else "SELL"
    return OpenPosition(
        entry_price=pos.average_price,
        quantity=pos.position_amount,
        side=side,
        stop_price=Decimal("0"),
        take_profit_price=None,
        entry_time_ms=pos.update_time_ms or 0,
    )


async def _candle_loop(
    *,
    args: argparse.Namespace,
    strategy: Any,
    state: RunnerState,
    private_api: PrivateAPI,
    stop_event: asyncio.Event,
) -> None:
    """Подписка на market WS + обработка закрытых свечей."""
    channel = f"{args.symbol}@kline_{args.interval}"
    async with BingXMarketWebSocket() as ws:
        iterator = await ws.subscribe(channel)
        async for msg in iterator:
            if stop_event.is_set():
                return
            if not isinstance(msg, dict):
                continue
            candle = _decode_kline_message(dict(msg))
            if candle is None:
                continue
            await _handle_closed_candle(candle, args, strategy, state, private_api)


async def _handle_closed_candle(
    candle: Kline,
    args: argparse.Namespace,
    strategy: Any,
    state: RunnerState,
    private_api: PrivateAPI,
) -> None:
    # Append + trim history к разумному размеру (warm-up * 2).
    state.candles_history.append(candle)
    max_history = max(args.warmup_candles * 2, 500)
    if len(state.candles_history) > max_history:
        state.candles_history = state.candles_history[-max_history:]

    ctx = StrategyContext(
        current_candle=candle,
        history=tuple(state.candles_history),
        equity=state.equity,
        open_position=state.open_position,
    )
    try:
        request = strategy.on_candle_close(ctx)
    except Exception:
        logger.exception("strategy.on_candle_close failed")
        return
    if request is None:
        return
    logger.info(
        "signal: %s %s qty=%s sl=%s",
        request.side,
        request.symbol,
        request.quantity,
        request.attached_stop_loss,
    )
    if args.dry_run:
        logger.warning("DRY-RUN: skipping place_order")
        return
    try:
        ack = await private_api.place_order(request, request_mark_price=candle.close)
        logger.info("order placed: %s status=%s", ack.order_id, ack.status)
    except Exception:
        logger.exception("place_order failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="BingX live runner")
    parser.add_argument(
        "--strategy",
        choices=["btc_breakout", "us_session_breakout", "trend_ema_4h"],
        required=True,
    )
    parser.add_argument("--symbol", default="BTC-USDT")
    parser.add_argument("--interval", default="15m")
    parser.add_argument(
        "--warmup-candles",
        type=int,
        default=300,
        help="Сколько свечей подтянуть через REST перед стартом WS",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только логировать сигналы, не отправлять ордера",
    )
    parser.add_argument(
        "--journal-db", default="ops/live-orders.sqlite"
    )
    parser.add_argument(
        "--metrics-file", default="ops/live-metrics.jsonl"
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
