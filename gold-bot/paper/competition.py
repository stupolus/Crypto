"""CompetitionRunner: champion + N challengers на одном потоке свечей.

См. plan 08. Каждая стратегия получает СВОЙ PaperJournal (отдельный SQLite
файл / in-memory), но один и тот же `PaperFeed` per symbol. Это исключает
«удача с тайминга»: champion и challengers видят те же свечи и те же
open-цены для fill'а.

Никаких реальных ордеров. Все participants — paper, движок — `PaperEngine`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from backtest.costs import CostModel
from backtest.strategy import Strategy
from exchanges.logging_utils import LOGGER_NAME
from exchanges.models import OHLCV
from paper.engine import EngineSnapshot, PaperEngine
from paper.feed import PaperFeed
from paper.journal import PaperJournal
from risk.config import RiskConfig

_log = logging.getLogger(LOGGER_NAME)


@dataclass(frozen=True)
class Participant:
    """Одна конкурирующая стратегия (champion или challenger)."""

    strategy_id: str
    journal: PaperJournal
    engine: PaperEngine


@dataclass(frozen=True)
class ParticipantSpec:
    """Описание участника на старте competition (без созданных движков)."""

    strategy_id: str
    journal_path: str
    strategy_factory: Callable[[str], Strategy]


def build_participant(
    spec: ParticipantSpec,
    symbol: str,
    cost_model: CostModel,
    risk_cfg: RiskConfig,
    starting_equity: Decimal,
) -> Participant:
    journal = PaperJournal(spec.journal_path)
    engine = PaperEngine(
        symbol=symbol,
        strategy=spec.strategy_factory(symbol),
        cost_model=cost_model,
        risk_cfg=risk_cfg,
        journal=journal,
        starting_equity=starting_equity,
    )
    return Participant(strategy_id=spec.strategy_id, journal=journal, engine=engine)


class CompetitionRunner:
    """Broadcast одного потока свечей в N движков.

    Контракт: ОДИН символ за раз. Multi-symbol — отдельный CompetitionRunner
    на каждый символ (так проще считать isolation: каждый журнал хранит
    только сделки своего символа).
    """

    def __init__(
        self,
        symbol: str,
        feed: PaperFeed,
        participants: list[Participant],
        history_seed: list[OHLCV] | None = None,
    ) -> None:
        if not participants:
            raise ValueError("competition требует хотя бы одного participant")
        ids = [p.strategy_id for p in participants]
        if len(set(ids)) != len(ids):
            raise ValueError(f"strategy_id должны быть уникальны: {ids}")
        self._symbol = symbol
        self._feed = feed
        self._participants = participants
        if history_seed:
            for p in participants:
                p.engine.seed_history(list(history_seed))

    @property
    def participants(self) -> list[Participant]:
        return list(self._participants)

    async def step(self) -> dict[str, list[EngineSnapshot]]:
        """Один цикл: вытащить новые закрытые свечи, прогнать через всех.

        Все participants видят свечи в одном и том же порядке. Each step
        возвращает snapshots по каждому strategy_id для логов.
        """
        per_participant_ts = [
            p.journal.get_last_candle_ts(self._symbol) for p in self._participants
        ]
        # минимальный last_seen среди всех; None трактуем как «нет истории».
        non_none = [ts for ts in per_participant_ts if ts is not None]
        last_ts_global = min(non_none) if non_none else None
        new_closed = await self._feed.fetch_new_closed(last_ts_global)
        results: dict[str, list[EngineSnapshot]] = {p.strategy_id: [] for p in self._participants}
        for candle in new_closed:
            for p in self._participants:
                # каждый participant обрабатывает свечу независимо
                last_p = p.journal.get_last_candle_ts(self._symbol)
                if last_p is not None and candle.timestamp <= last_p:
                    continue
                snap = p.engine.process_closed_candle(candle)
                results[p.strategy_id].append(snap)
                _log.info(
                    "competition.step symbol=%s strategy=%s ts=%s "
                    "closed=%s opened=%s rejected=%s equity=%s",
                    self._symbol,
                    p.strategy_id,
                    candle.timestamp,
                    snap.closed_trade is not None,
                    snap.opened_position is not None,
                    snap.rejected_reason,
                    snap.equity,
                )
        return results

    def close(self) -> None:
        for p in self._participants:
            p.journal.close()
