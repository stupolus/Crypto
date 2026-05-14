"""Past-Mistakes Retriever — поиск похожих ошибок по category+symbol.

Простая keyword-based реализация для MVP. FAISS / embedding similarity
(plan #18 §6.3) — отдельный PR, для него нужны embeddings и vector
store.

Сейчас retriever читает все loss-сделки из ``TradeOutcomeLogger`` и
возвращает топ-N по совпадению category (primary) + symbol. Category
извлекается из exit_reason (SL/TIMEOUT) — это коарсе классификация,
которая работает без LLM. Точная category из MistakeClassifierAgent
здесь не используется (нужен отдельный store для classification
results — добавим параллельно с FAISS).

Output → Past-Mistakes Context Injector → Coordinator prompt при новом
decision получает текстовое summary из топ-3 похожих past mistakes.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from core.postmortem.logger import TradeOutcomeLogger
from core.postmortem.models import TradeOutcome

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PastMistakeSummary:
    """Сжатая выжимка из TradeOutcome для подачи в Coordinator prompt.

    Не содержит full LLM payloads — только ключевые числа + 1-2 строки
    description. Coordinator prompt ограничен в context window.
    """

    trade_id: str
    symbol: str
    side: str
    exit_reason: str
    pnl_pct: Decimal
    holding_time_min: int
    summary: str


class PastMistakesRetriever:
    """Keyword-based retriever ошибок прошлых сделок.

    DI logger через конструктор. Метод ``find_similar`` возвращает топ-N
    похожих по (symbol == query_symbol) и exit_reason ∈ allowed_exits.

    Использование::

        retriever = PastMistakesRetriever(logger)
        similar = retriever.find_similar(
            symbol="BTC-USDT",
            limit=3,
        )
        for s in similar:
            print(s.summary)  # текст для prompt'а
    """

    def __init__(self, outcome_logger: TradeOutcomeLogger) -> None:
        self._logger = outcome_logger

    def find_similar(
        self,
        *,
        symbol: str,
        limit: int = 3,
        exit_reasons: Sequence[str] = ("SL", "TIMEOUT"),
    ) -> list[PastMistakeSummary]:
        """Найти похожие убыточные сделки.

        Args:
            symbol: текущий символ (e.g. "BTC-USDT").
            limit: сколько summary вернуть.
            exit_reasons: фильтр по exit_reason. Default — все exits
                которые мы считаем mistake-driven (SL и TIMEOUT).
                Manual / RISK_OFF — внешние причины, не считаем.

        Returns:
            Список ``PastMistakeSummary`` (≤ limit) отсортированный
            DESC по exit_time_ms — свежие ошибки сначала.
        """
        if limit <= 0:
            return []

        # Берём больше из БД (по убыванию exit_time), потом фильтруем
        # in-memory — recent_losses уже DESC ordered.
        candidates = self._logger.recent_losses(limit=limit * 10)
        filtered: list[PastMistakeSummary] = []
        for outcome in candidates:
            if outcome.symbol != symbol:
                continue
            if outcome.exit_reason not in exit_reasons:
                continue
            summary = _build_summary(outcome)
            filtered.append(summary)
            if len(filtered) >= limit:
                break

        logger.debug(
            "past_mistakes: %d/%d matches for symbol=%s",
            len(filtered),
            len(candidates),
            symbol,
        )
        return filtered


def _build_summary(outcome: TradeOutcome) -> PastMistakeSummary:
    """Конвертация TradeOutcome → PastMistakeSummary (сжатая форма).

    ``summary`` — 1-2 строки natural language для подачи в Coordinator.
    """
    assert outcome.exit_reason is not None  # из exit_reasons filter
    assert outcome.pnl_pct is not None
    assert outcome.holding_time_min is not None

    summary_text = (
        f"{outcome.side} {outcome.symbol} → {outcome.exit_reason} за "
        f"{outcome.holding_time_min}мин, PnL={outcome.pnl_pct}%"
    )
    return PastMistakeSummary(
        trade_id=outcome.trade_id,
        symbol=outcome.symbol,
        side=outcome.side,
        exit_reason=outcome.exit_reason,
        pnl_pct=outcome.pnl_pct,
        holding_time_min=outcome.holding_time_min,
        summary=summary_text,
    )


def summaries_to_prompt_text(summaries: list[PastMistakeSummary]) -> str:
    """Отформатировать summaries в кусок текста для Coordinator prompt'а.

    Использование::

        similar = retriever.find_similar(symbol="BTC-USDT")
        past_mistakes_text = summaries_to_prompt_text(similar)
        # → "Past mistakes: ...\\n- ...\\n- ..."

        coordinator_context["past_mistakes"] = past_mistakes_text

    Пустой list → пустая строка (Coordinator promtp обработает defaults).
    """
    if not summaries:
        return ""
    lines = ["Past mistakes on same symbol (most recent first):"]
    for s in summaries:
        lines.append(f"- {s.summary}")
    return "\n".join(lines)
