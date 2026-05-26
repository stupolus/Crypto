"""PaperRunner: оркестратор feed → engine → journal/reporter.

Один процесс может вести несколько символов (PAXG/USDT, XAUT/USDT и т.д.):
на каждый символ — отдельный PaperEngine + PaperFeed + история истории
свечей. RiskState формально per-engine (в v1); общий cross-symbol risk —
отдельный план (после первого месяца paper).

Никаких реальных ордеров. Адаптер используется только для fetch_markets
и fetch_ohlcv (это enforced ещё и в plan 06 §«Ключевые инварианты»).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from backtest.costs import CostModel
from backtest.strategy import Strategy
from exchanges.logging_utils import LOGGER_NAME
from exchanges.models import OHLCV
from marketdata.candles import timeframe_to_ms
from paper.config import PaperConfig
from paper.engine import EngineSnapshot, PaperEngine
from paper.feed import PaperFeed
from paper.journal import PaperJournal
from paper.reporter import NullReporter, Reporter
from risk.config import RiskConfig


class _OhlcvSource(Protocol):
    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, since: int | None = None, limit: int | None = None
    ) -> list[OHLCV]: ...


@dataclass(frozen=True)
class SymbolRunner:
    symbol: str
    feed: PaperFeed
    engine: PaperEngine


class PaperRunner:
    def __init__(
        self,
        adapter: _OhlcvSource,
        cfg: PaperConfig,
        risk_cfg: RiskConfig,
        strategy_factory: Callable[[str], Strategy],
        journal: PaperJournal,
        reporter: Reporter | None = None,
        history_warmup: int = 200,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._adapter = adapter
        self._cfg = cfg
        self._risk_cfg = risk_cfg
        self._journal = journal
        self._reporter = reporter or NullReporter()
        self._log = logging.getLogger(LOGGER_NAME)
        self._history_warmup = max(50, history_warmup)
        self._clock = clock or (lambda: int(time.time() * 1000))
        costs = CostModel(taker_fee=cfg.taker_fee, slippage_pct=cfg.slippage_pct)
        self._symbol_runners: list[SymbolRunner] = []
        for symbol in cfg.symbols:
            engine = PaperEngine(
                symbol=symbol,
                strategy=strategy_factory(symbol),
                cost_model=costs,
                risk_cfg=risk_cfg,
                journal=journal,
                starting_equity=cfg.starting_equity,
            )
            feed = PaperFeed(
                adapter=adapter,
                symbol=symbol,
                timeframe=cfg.timeframe,
                close_grace_ms=cfg.close_grace_seconds * 1000,
                clock=self._clock,
            )
            self._symbol_runners.append(SymbolRunner(symbol=symbol, feed=feed, engine=engine))

    async def warmup(self) -> None:
        """Подтянуть последние свечи на каждый символ, чтобы стратегия имела
        достаточную историю на первой итерации (vwap_window, atr_period)."""
        tf_ms = timeframe_to_ms(self._cfg.timeframe)
        for sr in self._symbol_runners:
            since = self._clock() - self._history_warmup * tf_ms
            raw = await self._adapter.fetch_ohlcv(
                sr.symbol, self._cfg.timeframe, since=since, limit=self._history_warmup
            )
            # отбрасываем последнюю «не закрытую» свечу если она ещё не закрыта
            now = self._clock()
            closed = [c for c in raw if c.timestamp + tf_ms + 1000 <= now]
            sr.engine.seed_history(closed)
            self._log.info(
                "paper.warmup symbol=%s history=%d last_ts=%s",
                sr.symbol,
                len(closed),
                closed[-1].timestamp if closed else None,
            )

    async def step(self) -> list[EngineSnapshot]:
        """Один цикл polling по всем символам. Возвращает все snapshot'ы."""
        snapshots: list[EngineSnapshot] = []
        for sr in self._symbol_runners:
            last_ts = self._journal.get_last_candle_ts(sr.symbol)
            new_closed = await sr.feed.fetch_new_closed(last_ts)
            for candle in new_closed:
                snap = sr.engine.process_closed_candle(candle)
                snapshots.append(snap)
                self._on_snapshot(sr.symbol, candle, snap)
        self._journal.heartbeat(self._clock())
        return snapshots

    def _on_snapshot(self, symbol: str, candle: OHLCV, snap: EngineSnapshot) -> None:
        if snap.closed_trade is not None:
            t = snap.closed_trade
            self._log.info(
                "paper.trade symbol=%s side=%s entry=%s exit=%s qty=%s pnl=%s reason=%s equity=%s",
                t.symbol,
                t.side.value,
                t.entry_price,
                t.exit_price,
                t.quantity,
                t.net_pnl,
                t.exit_reason,
                t.equity_after,
            )
            self._reporter.send(
                f"[paper] {t.symbol} {t.side.value} closed "
                f"pnl={t.net_pnl} reason={t.exit_reason} equity={t.equity_after}"
            )
        if snap.opened_position is not None:
            p = snap.opened_position
            self._log.info(
                "paper.open symbol=%s side=%s entry=%s qty=%s stop=%s tp=%s",
                p.symbol,
                p.side.value,
                p.entry_price,
                p.quantity,
                p.stop,
                p.take_profit,
            )
        if snap.rejected_reason is not None:
            self._log.warning(
                "paper.rejected symbol=%s ts=%s reason=%s",
                symbol,
                candle.timestamp,
                snap.rejected_reason,
            )

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        await self.warmup()
        self._reporter.send(
            f"[paper] runner started symbols={','.join(self._cfg.symbols)} "
            f"tf={self._cfg.timeframe} equity={self._symbol_runners[0].engine.equity}"
        )
        try:
            while stop_event is None or not stop_event.is_set():
                try:
                    await self.step()
                except Exception:
                    self._log.exception("paper.step.failed")
                await asyncio.sleep(self._cfg.poll_interval_seconds)
        finally:
            self._reporter.send("[paper] runner stopped")

    def daily_summary(self) -> str:
        today = datetime.now(tz=UTC).date()
        trades = self._journal.list_trades(today)
        if not trades:
            return f"[paper] daily {today.isoformat()}: 0 trades"
        wins = sum(1 for t in trades if t.net_pnl > 0)
        gross = sum((t.gross_pnl for t in trades), Decimal(0))
        costs = sum((t.costs for t in trades), Decimal(0))
        net = sum((t.net_pnl for t in trades), Decimal(0))
        equity_close = trades[-1].equity_after
        self._journal.upsert_daily_summary(
            today, len(trades), wins, gross, costs, net, equity_close
        )
        return (
            f"[paper] daily {today.isoformat()}: trades={len(trades)} "
            f"wins={wins} net={net} equity={equity_close}"
        )
