"""LLM-runner: live_runner + LLM Gate (Layer 3) перед каждой сделкой.

Расширение ``live_runner.py``: между ``strategy.on_candle_close`` и
``private_api.place_order`` вставляется ``llm_gate`` — пятерка LLM-агентов
(Market / Sentiment / Risk / Macro / Coordinator) проверяет каждый сигнал
Layer 2 стратегии. Только сигналы с ``action != HOLD`` и совпадающим
``side`` уходят в Risk Engine + Execution.

Использование::

    .venv/bin/python -m runners.llm_runner \\
        --strategy btc_breakout \\
        --symbol BTC-USDT \\
        --interval 15m \\
        --token BTC

**Запускать только на VST** до явного решения по live. Layer 3 требует
``ANTHROPIC_API_KEY`` в .env, иначе ``AgentFactoryError`` на старте.

Опциональные источники (включаются если есть ключи в .env):
- ``FRED_API_KEY`` → реальные macro indicators через FRED
- ``GROQ_API_KEY`` + ``APIFY_TOKEN`` → Twitter sentiment через Layer 1

Без них builder возвращает defaults ("0" / "neutral") — Layer 3 промпты
тренировались на этих placeholder'ах и обрабатывают.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from contextlib import suppress
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from adapters.bingx.client import BingXClient
from adapters.bingx.exceptions import AuthError, OrderRejected
from adapters.bingx.journal import OrderJournal
from adapters.bingx.metrics import MetricsWriter
from adapters.bingx.models import Kline
from adapters.bingx.private import PrivateAPI
from adapters.bingx.private_models import OrderUpdateEvent
from adapters.bingx.public import PublicAPI
from adapters.bingx.settings import BingXSettings
from adapters.bingx.user_stream import BingXUserDataStream
from adapters.bingx.websocket import BingXMarketWebSocket
from core.agents.evaluate import RunnerStateSnapshot, SentimentContextData
from core.agents.factory import AgentFactoryError, build_default_team
from core.agents.llm_gate import llm_gate
from core.agents.market_context_builder import MarketContextBuilder
from core.agents.team import AgentTeam
from core.alerts import Alerter
from core.backtest.models import StrategyContext
from core.postmortem import (
    DecisionContext,
    ExitTracker,
    PastMistakesRetriever,
    TradeOutcomeLogger,
    summaries_to_prompt_text,
)
from core.risk import RiskEngine, check_correlation
from core.safety import HaltFlag
from parsers.macro.context_builder import MacroContextBuilder
from parsers.macro.factory import FREDFactoryError, build_fred_adapter_from_env
from parsers.macro.fred_adapter import FREDAdapter
from parsers.macro.yahoo_http_fetcher import YahooHttpFetcher
from parsers.macro.yfinance_adapter import YfinanceAdapter
from runners.live_runner import (
    RunnerState,
    _build_alerter,
    _build_strategy,
    _fetch_equity,
    _handle_user_event,
    _heartbeat_loop,
    _install_signal_handlers,
    _interval_to_ms,
    _KlineCloseDetector,
    _warm_history,
)

logger = logging.getLogger(__name__)


class _NoopFREDFetcher:
    """Stub реализация FREDFetcher Protocol — пустой dict, используется
    когда FRED_API_KEY отсутствует."""

    def fetch_latest(self, series_ids: list[str]) -> dict[str, Decimal]:
        return {}


def _build_decision_context(
    *,
    trade_id: str,
    approved: Any,
    gate_result: Any,
    candle: Kline,
) -> DecisionContext:
    """Собрать DecisionContext для TradeOutcomeLogger.record_entry.

    Берём:
    - trade_id из BingX order_id (после успешного place_order)
    - entry_price из approved.price (LIMIT) или candle.close (MARKET)
    - size из approved.quantity
    - LLM payload'ы из gate_result.decision.subagent_payloads + coordinator
    - signal_candidate из gate_result.decision (signal context был передан)
    """
    entry_price = approved.price if approved.price is not None else candle.close
    payloads = gate_result.decision.subagent_payloads
    coordinator = gate_result.decision.coordinator_payload
    return DecisionContext(
        trade_id=trade_id,
        symbol=approved.symbol,
        side=approved.side,
        entry_time_ms=int(time.time() * 1000),
        entry_price=entry_price,
        size=approved.quantity,
        signal_candidate={
            "symbol": approved.symbol,
            "action": approved.side,
            "proposed_entry": str(entry_price),
            "proposed_sl": str(approved.attached_stop_loss),
        },
        market_analyst=payloads.get("market", {}),
        sentiment_analyst=payloads.get("sentiment", {}),
        risk_overseer=payloads.get("risk", {}),
        macro_analyst=payloads.get("macro", {}),
        coordinator=coordinator,
        latency_decision_ms=gate_result.decision.total_latency_ms,
    )


def _build_runner_state_snapshot(state: RunnerState) -> RunnerStateSnapshot:
    """Конвертировать RunnerState (live_runner) → RunnerStateSnapshot (Layer 3)."""
    open_positions: tuple[dict[str, Any], ...] = ()
    if state.open_position is not None:
        op = state.open_position
        open_positions = (
            {
                "symbol": "BTC-USDT",  # из args — но не критично для Risk Overseer
                "side": op.side,
                "entry_price": str(op.entry_price),
                "quantity": str(op.quantity),
                "stop_price": str(op.stop_price),
                "take_profit_price": (str(op.take_profit_price) if op.take_profit_price else "0"),
            },
        )
    return RunnerStateSnapshot(
        equity=state.equity,
        daily_pnl_pct=Decimal("0"),  # TODO: реальный PnL через journal/metrics
        open_positions=open_positions,
    )


async def _handle_closed_candle_with_llm(
    candle: Kline,
    args: argparse.Namespace,
    strategy: Any,
    state: RunnerState,
    private_api: PrivateAPI,
    alerter: Alerter,
    team: AgentTeam,
    macro_builder: MacroContextBuilder,
    market_builder: MarketContextBuilder,
    outcome_logger: TradeOutcomeLogger | None = None,
    past_mistakes_retriever: PastMistakesRetriever | None = None,
    exit_tracker: ExitTracker | None = None,
    halt_flag: HaltFlag | None = None,
) -> None:
    """Закрытая свеча → strategy → llm_gate → place_order.

    Расширение ``_handle_closed_candle`` из live_runner: перед отправкой
    OrderRequest на биржу прогоняем через AgentTeam. После APPROVED +
    успешного place_order сохраняем DecisionContext в Layer 6 journal
    (если outcome_logger передан).

    Если ``past_mistakes_retriever`` передан — для каждого raw signal
    логируем top-N похожих past mistakes из истории (Layer 6 feedback
    loop). Реальная инъекция в Coordinator prompt — отдельный PR с
    обновлением промпта (требует accept нового поля past_mistakes).
    """
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
    except Exception as exc:
        logger.exception("strategy.on_candle_close failed")
        await alerter.send_critical(f"strategy.on_candle_close failed: {exc}")
        return
    if request is None:
        return

    # Session window check: некоторые asset classes торгуются только в окне
    # (stock_perp = NY hours, commodity = Mon-Fri). Сигнал вне окна → skip.
    try:
        from core.assets import is_session_open

        if not is_session_open(request.symbol):
            logger.info(
                "session closed for %s — skipping signal (out-of-hours)",
                request.symbol,
            )
            return
    except Exception:
        # Asset не зарегистрирован → 24/7 fallback (как было до multi-asset)
        pass

    # Emergency halt check: если флаг существует, не открываем новую сделку.
    # Открытые позиции защищены биржевыми SL/TP, их не трогаем.
    if halt_flag is not None and halt_flag.is_set():
        reason = halt_flag.read_reason()
        reason_str = f"{reason.source}: {reason.note}" if reason else "unknown"
        logger.warning(
            "HALT flag active — skipping signal %s %s (reason: %s)",
            request.side,
            request.symbol,
            reason_str,
        )
        await alerter.send_warning(
            f"HALT active on {request.symbol} ({reason_str}) — signal skipped"
        )
        return

    logger.info(
        "strategy raw signal: %s %s qty=%s sl=%s — passing to LLM gate",
        request.side,
        request.symbol,
        request.quantity,
        request.attached_stop_loss,
    )

    # Layer 6 feedback: собираем past mistakes для injection в Coordinator.
    past_mistakes_text = ""
    if past_mistakes_retriever is not None:
        try:
            similar = past_mistakes_retriever.find_similar(symbol=request.symbol, limit=3)
            past_mistakes_text = summaries_to_prompt_text(similar)
            if similar:
                logger.info("past mistakes context:\n%s", past_mistakes_text)
            else:
                logger.debug("past mistakes: нет похожих на %s", request.symbol)
        except Exception:
            logger.exception("past_mistakes_retriever.find_similar failed")

    market_data = market_builder.build(history=state.candles_history)
    macro_data = await macro_builder.build()
    sentiment_data = SentimentContextData()  # пока stub; SentimentContextBuilder отдельно
    state_snapshot = _build_runner_state_snapshot(state)

    try:
        gate_result = await llm_gate(
            team=team,
            order_request=request,
            strategy_name=args.strategy,
            timestamp_ms=int(time.time() * 1000),
            indicators={
                "atr": market_data.atr,
                "donchian_high": market_data.donchian_high,
                "donchian_low": market_data.donchian_low,
                "ema20": market_data.ema20,
                "ema50": market_data.ema50,
            },
            confidence_raw=0.7,  # пока константа, можно прокинуть от стратегии
            state=state_snapshot,
            market_data=market_data,
            sentiment_data=sentiment_data,
            macro_data=macro_data,
            past_mistakes=past_mistakes_text,
        )
    except Exception as exc:
        logger.exception("llm_gate failed — defensively skipping signal")
        await alerter.send_warning(f"llm_gate failed on {request.symbol}: {exc} — skipping")
        return

    if gate_result.approved_request is None:
        logger.info(
            "LLM gate veto: reason=%s coordinator_action=%s confidence=%s",
            gate_result.reason,
            gate_result.decision.coordinator_payload.get("action"),
            gate_result.decision.coordinator_payload.get("composite_confidence"),
        )
        return

    approved = gate_result.approved_request
    logger.info(
        "LLM gate APPROVED: %s %s qty=%s sl=%s tp=%s",
        approved.side,
        approved.symbol,
        approved.quantity,
        approved.attached_stop_loss,
        approved.attached_take_profit,
    )

    if args.dry_run:
        logger.warning("DRY-RUN: skipping place_order")
        return

    # Correlation gate: max 1 открытая позиция на asset class.
    # Runner'ы независимы — этот чек видит позиции ДРУГИХ runner'ов
    # через общий BingX-аккаунт. Политика: разные группы — разные позиции.
    try:
        all_positions = await private_api.get_positions(symbol=None)
        corr = check_correlation(approved.symbol, list(all_positions))
        if not corr.allowed:
            logger.info("correlation gate blocked %s: %s", approved.symbol, corr.reason)
            await alerter.send_info(f"correlation gate skip: {corr.reason}")
            return
    except Exception as exc:
        # Не валим runner если positions-запрос упал — лог + продолжаем.
        # RiskEngine + strategy state machine остаются как защита.
        logger.warning("correlation gate check failed (continuing): %s", exc)

    # Диагностический dump перед place_order. Помогает понять что именно
    # отправляем на BingX когда ответ — 101429 (position limit exceeded) или
    # 101400 (SL wrong side). Видно qty/SL/TP/entry в одной строке.
    logger.info(
        "place_order request: symbol=%s side=%s type=%s qty=%s entry_mark=%s sl=%s tp=%s coid=%s",
        approved.symbol,
        approved.side,
        approved.order_type,
        approved.quantity,
        candle.close,
        approved.attached_stop_loss,
        approved.attached_take_profit,
        approved.client_order_id,
    )
    try:
        ack = await private_api.place_order(approved, request_mark_price=candle.close)
        logger.info("order placed: %s status=%s", ack.order_id, ack.status)
    except OrderRejected as exc:
        logger.error("OrderRejected: %s", exc)
        await alerter.send_critical(f"OrderRejected on {approved.symbol}: {exc}")
        return
    except AuthError as exc:
        logger.exception("AuthError")
        await alerter.send_critical(f"AuthError on {approved.symbol}: {exc}. Stopping runner.")
        raise
    except Exception as exc:
        # Включаем диагностику в alert на случай если log не дойдёт.
        logger.exception("place_order failed")
        await alerter.send_warning(
            f"place_order failed on {approved.symbol}: {exc} "
            f"[qty={approved.quantity} sl={approved.attached_stop_loss} "
            f"tp={approved.attached_take_profit} mark={candle.close}]"
        )
        return

    # Layer 6 capture: записываем DecisionContext только если ордер реально размещён.
    if outcome_logger is not None:
        try:
            decision_ctx = _build_decision_context(
                trade_id=ack.order_id,
                approved=approved,
                gate_result=gate_result,
                candle=candle,
            )
            outcome_logger.record_entry(decision_ctx)
        except Exception as exc:
            # Layer 6 ошибка не должна блокировать торговлю.
            logger.exception("outcome_logger.record_entry failed: %s", exc)

    # Layer 6 exit tracking: regisrer открытую сделку чтобы потом её закрытие
    # триггерило record_exit.
    if exit_tracker is not None:
        try:
            exit_tracker.register_entry(
                trade_id=ack.order_id,
                symbol=approved.symbol,
                entry_price=approved.price if approved.price is not None else candle.close,
                size=approved.quantity,
                entry_time_ms=int(time.time() * 1000),
            )
        except Exception:
            logger.exception("exit_tracker.register_entry failed")


async def _user_events_loop_with_tracker(
    stream: Any,
    strategy: Any,
    state: RunnerState,
    journal: Any,
    *,
    outcome_logger: TradeOutcomeLogger | None,
    exit_tracker: ExitTracker | None,
) -> None:
    """Расширение live_runner._user_events_loop с Layer 6 exit tracking.

    Делегирует основное поведение _handle_user_event, потом добавляет
    ExitTracker.observe_order_event на каждый OrderUpdateEvent.
    """
    async for event in stream.events():
        try:
            await _handle_user_event(event, strategy, state, journal)
        except Exception:
            logger.exception("user event handler error for %r", event)
            continue
        # Layer 6 exit detection: только OrderUpdateEvent + tracker.
        if (
            exit_tracker is None
            or outcome_logger is None
            or not isinstance(event, OrderUpdateEvent)
        ):
            continue
        try:
            result = exit_tracker.observe_order_event(event)
            if result is not None:
                trade_id, exit_data = result
                outcome_logger.record_exit(trade_id, exit_data)
                logger.info(
                    "Layer 6: record_exit %s reason=%s pnl=%s%%",
                    trade_id,
                    exit_data.exit_reason,
                    exit_data.pnl_pct,
                )
        except Exception:
            logger.exception("exit_tracker / record_exit failed for event %r", event)


async def _equity_snapshot_loop(
    snapshot_path: Path,
    private_api: PrivateAPI,
    stop_event: asyncio.Event,
    interval_s: float = 300.0,
) -> None:
    """Периодически пишет {timestamp_ms, equity} в jsonl.

    Даёт настоящую equity-curve в дашборде (vs текущая реконструкция
    из closed-trade PnL, которая игнорирует unrealized P&L и депозиты).

    Best-effort: ошибки сети/диска логируются, не валят runner.
    """
    import json as _json

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    while not stop_event.is_set():
        try:
            equity = await _fetch_equity(private_api)
            line = _json.dumps({"timestamp_ms": int(time.time() * 1000), "equity": str(equity)})
            with snapshot_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            logger.warning("equity snapshot failed: %s", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except TimeoutError:
            continue


async def _candle_loop_llm(
    *,
    args: argparse.Namespace,
    strategy: Any,
    state: RunnerState,
    private_api: PrivateAPI,
    stop_event: asyncio.Event,
    alerter: Alerter,
    team: AgentTeam,
    macro_builder: MacroContextBuilder,
    market_builder: MarketContextBuilder,
    outcome_logger: TradeOutcomeLogger | None,
    past_mistakes_retriever: PastMistakesRetriever | None,
    exit_tracker: ExitTracker | None,
    halt_flag: HaltFlag | None,
) -> None:
    interval_ms = _interval_to_ms(args.interval)
    channel = f"{args.symbol}@kline_{args.interval}"
    detector = _KlineCloseDetector(interval_ms)
    async with BingXMarketWebSocket() as ws:
        iterator = await ws.subscribe(channel)
        async for msg in iterator:
            if stop_event.is_set():
                return
            if not isinstance(msg, dict):
                continue
            try:
                closed = detector.feed(dict(msg))
            except Exception:
                logger.exception("failed to detect closed kline")
                continue
            if closed is None:
                continue
            logger.info("candle closed: %s c=%s", args.symbol, closed.close)
            await _handle_closed_candle_with_llm(
                closed,
                args,
                strategy,
                state,
                private_api,
                alerter,
                team,
                macro_builder,
                market_builder,
                outcome_logger,
                past_mistakes_retriever,
                exit_tracker,
                halt_flag,
            )


async def run(args: argparse.Namespace) -> None:
    settings = BingXSettings()
    if settings.env == "live":
        raise SystemExit(
            "Refusing to run on live without --i-know-what-im-doing. Set BINGX_ENV=vst in .env."
        )

    # AgentTeam — обязательное условие, без ANTHROPIC_API_KEY runner стартовать не должен
    try:
        async with httpx.AsyncClient(timeout=60.0) as agent_http:
            team = build_default_team(client=agent_http)
            await _run_with_team(args, team)
    except AgentFactoryError as e:
        raise SystemExit(f"LLM runner требует ANTHROPIC_API_KEY: {e}") from e


async def _run_with_team(args: argparse.Namespace, team: AgentTeam) -> None:
    settings = BingXSettings()
    journal_path = Path(args.journal_db)
    metrics_path = Path(args.metrics_file)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)

    journal = OrderJournal(journal_path)
    metrics = MetricsWriter(metrics_path)

    risk = RiskEngine()
    strategy = _build_strategy(args.strategy, risk)
    logger.info("strategy initialized: %s", args.strategy)

    # Macro: yfinance (через httpx Yahoo quote API, без яндекс-deps) + FRED
    yf = YfinanceAdapter(fetcher=YahooHttpFetcher())
    logger.info("Yahoo fetcher: HTTP (DXY/VIX/SPX/NDX/Gold/Oil/^TNX live)")
    try:
        fred = build_fred_adapter_from_env()
        logger.info("FRED adapter built from env")
    except FREDFactoryError as e:
        logger.warning("FRED disabled (no API key): %s — macro работает без FRED", e)
        fred = FREDAdapter(fetcher=_NoopFREDFetcher())

    macro_builder = MacroContextBuilder(yf, fred)
    market_builder = MarketContextBuilder()

    outcome_logger: TradeOutcomeLogger | None = None
    past_mistakes_retriever: PastMistakesRetriever | None = None
    exit_tracker: ExitTracker | None = None
    if args.outcomes_db:
        outcome_logger = TradeOutcomeLogger(Path(args.outcomes_db))
        past_mistakes_retriever = PastMistakesRetriever(outcome_logger)
        exit_tracker = ExitTracker()
        logger.info(
            "Layer 6 enabled: outcome_logger + past_mistakes + exit_tracker (%s)",
            args.outcomes_db,
        )

    halt_flag: HaltFlag | None = None
    if args.halt_flag_file:
        halt_flag = HaltFlag(Path(args.halt_flag_file))
        if halt_flag.is_set():
            reason = halt_flag.read_reason()
            logger.warning(
                "HALT flag already set on startup: %s",
                f"{reason.source}: {reason.note}" if reason else "unknown",
            )
        logger.info("Safety: halt_flag enabled (%s)", args.halt_flag_file)

    async with BingXClient(settings=settings) as client:
        public_api = PublicAPI(client, client.config)
        private_api = PrivateAPI(client, journal=journal, metrics=metrics)

        # CRITICAL: явно выставить плечо для символа.
        # CLAUDE.md / риск-профиль: max 5x crypto, 3x для TradFi (overnight gap).
        # Без этого BingX использует дефолт аккаунта (часто 10x) — silent risk.
        # Asset-specific cap из registry, потом cap CLI args.max_leverage.
        try:
            from core.assets import DEFAULT_REGISTRY

            asset_cfg = DEFAULT_REGISTRY.get(args.symbol)
            asset_cap = asset_cfg.max_leverage
        except Exception:
            asset_cap = 5  # crypto fallback
        leverage = max(1, min(args.max_leverage, asset_cap))
        try:
            await private_api.set_leverage(args.symbol, leverage, "BOTH")
            logger.info(
                "leverage set: %s @ %dx (BOTH) [asset_cap=%d, cli=%d]",
                args.symbol,
                leverage,
                asset_cap,
                args.max_leverage,
            )
        except Exception as exc:
            logger.error("set_leverage failed for %s: %s", args.symbol, exc)
            # Не start'уем без правильного плеча — это критичная safety
            raise SystemExit(
                f"Cannot set leverage on {args.symbol}: {exc}. "
                f"Без явного плеча есть риск что биржа применит default 10x+. "
                f"Проверь API permissions и валидность аккаунта."
            ) from exc

        history = await _warm_history(
            public_api, args.symbol, args.interval, count=args.warmup_candles
        )
        equity = await _fetch_equity(private_api)
        logger.info("starting equity: %s", equity)

        state = RunnerState(candles_history=history, equity=equity)

        stop_event = asyncio.Event()
        _install_signal_handlers(stop_event)

        alerter = _build_alerter(prefix=f"[llm@{args.strategy}@{args.symbol}]")
        await alerter.send_info(
            f"llm-runner starting: strategy={args.strategy} symbol={args.symbol}"
        )

        async with BingXUserDataStream(private_api) as user_stream:
            user_task = asyncio.create_task(
                _user_events_loop_with_tracker(
                    user_stream,
                    strategy,
                    state,
                    journal,
                    outcome_logger=outcome_logger,
                    exit_tracker=exit_tracker,
                ),
                name="llm-user-stream",
            )
            heartbeat_task: asyncio.Task[None] | None = None
            if args.heartbeat_file:
                heartbeat_task = asyncio.create_task(
                    _heartbeat_loop(Path(args.heartbeat_file), stop_event),
                    name="llm-heartbeat",
                )
            equity_task: asyncio.Task[None] | None = None
            if args.equity_snapshot_file:
                equity_task = asyncio.create_task(
                    _equity_snapshot_loop(Path(args.equity_snapshot_file), private_api, stop_event),
                    name="llm-equity-snapshot",
                )

            try:
                await _candle_loop_llm(
                    args=args,
                    strategy=strategy,
                    state=state,
                    private_api=private_api,
                    stop_event=stop_event,
                    alerter=alerter,
                    team=team,
                    macro_builder=macro_builder,
                    market_builder=market_builder,
                    outcome_logger=outcome_logger,
                    past_mistakes_retriever=past_mistakes_retriever,
                    exit_tracker=exit_tracker,
                    halt_flag=halt_flag,
                )
            finally:
                stop_event.set()
                user_task.cancel()
                with suppress(asyncio.CancelledError):
                    await user_task
                if heartbeat_task is not None:
                    heartbeat_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await heartbeat_task
                if equity_task is not None:
                    equity_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await equity_task
                await alerter.send_info(
                    f"llm-runner stopped: strategy={args.strategy} symbol={args.symbol}"
                )

    logger.info("llm runner stopped cleanly")


def main() -> None:
    parser = argparse.ArgumentParser(description="BingX live runner с LLM Gate (Layer 3)")
    parser.add_argument(
        "--strategy",
        choices=[
            "btc_breakout",
            "us_session_breakout",
            "trend_ema_4h",
            "gold_safety_haven",
            "oil_eia_avoid",
            "stock_earnings_avoid",
            "liquidation_reversal",
        ],
        required=True,
    )
    parser.add_argument("--symbol", default="BTC-USDT")
    parser.add_argument(
        "--token", default="BTC", help="Token для SentimentContextBuilder (BTC/ETH/...)"
    )
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--warmup-candles", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--journal-db", default="ops/llm-orders.sqlite")
    parser.add_argument("--metrics-file", default="ops/llm-metrics.jsonl")
    parser.add_argument(
        "--outcomes-db",
        default="ops/llm-outcomes.sqlite",
        help="Путь к Layer 6 TradeOutcomeLogger БД. Пустая строка отключает.",
    )
    parser.add_argument(
        "--halt-flag-file",
        default="/var/lib/crypto/halt",
        help="Path to emergency halt flag. Если файл exists — runner отказывается "
        "открывать новые сделки. touch файла = emergency stop без kill systemd. "
        "Пустая строка отключает проверку.",
    )
    parser.add_argument("--heartbeat-file", default=None)
    parser.add_argument(
        "--equity-snapshot-file",
        default=None,
        help="Если задан — каждые 5 мин пишем {ts_ms, equity} jsonl. "
        "Дашборд строит настоящую equity-curve вместо реконструкции из PnL.",
    )
    parser.add_argument(
        "--max-leverage",
        type=int,
        default=5,
        help=(
            "Максимальное плечо (cap 1-5x). Выставляется ЯВНО на бирже до "
            "первой сделки. CLAUDE.md требует ≤5x. По умолчанию 5x. "
            "Меньшие значения = более консервативно (1x = no leverage)."
        ),
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
