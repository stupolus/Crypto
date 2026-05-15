"""Mistake Classifier — LLM-классификатор убыточных сделок (plan #18 §6.2).

После закрытия каждой loss-сделки (PnL < 0) запускаем этот агент.
Получает TradeOutcome полностью (signal context + все 5 субагент-payload'ов
+ exit data) и возвращает структурированную классификацию ошибки.

Output → Mistake document (Markdown) → vector store (FAISS, отдельный PR)
→ Past-Mistakes Context Injector подсовывает топ-3 похожих past mistakes
в Coordinator prompt при новом decision.

Стоимость: ~$0.05/убыточная сделка (Sonnet 4.6). При 30% win-rate и
60 сделок/мес = 42 × $0.05 = ~$2.10/мес.
"""

from __future__ import annotations

from typing import Any

from core.agents.anthropic import AnthropicAgent
from core.agents.base import AgentExecutionError
from core.postmortem.models import TradeOutcome

_MISTAKE_CATEGORIES = {
    "signal_wrong",
    "sentiment_wrong",
    "market_regime_changed",
    "slippage_high",
    "risk_overlooked",
    "execution_late",
    "tp_too_aggressive",
    "sl_too_tight",
    "correlation_overlooked",
    "macro_event_missed",
}


class MistakeClassifierAgent(AnthropicAgent):
    """LLM-классификатор loss-сделок по 10 категориям ошибок.

    Контекст для ``user_prompt_template`` (обязательные ключи):
    - ``trade_id``, ``symbol``, ``side``
    - ``entry_price``, ``exit_price``, ``pnl_pct``, ``exit_reason``
    - ``holding_time_min``
    - ``signal_json``, ``market_json``, ``sentiment_json``,
      ``risk_json``, ``macro_json``, ``coordinator_json``

    Output JSON keys:
    - ``primary_category`` (один из 10)
    - ``secondary_categories`` (list, может быть пуст)
    - ``what_went_wrong`` (1-2 строки)
    - ``what_we_should_have_seen`` (1-2 строки)
    - ``confidence_in_diagnosis`` (0..1)
    """

    name = "mistake_classifier"
    model = "claude-sonnet-4-6"
    max_tokens = 1024

    system_prompt = (
        "Ты — senior portfolio manager делающий пост-мортем убыточной "
        "сделки крипто-бота. Получаешь полный контекст: signal candidate, "
        "решения 5 субагентов (Market / Sentiment / Risk / Macro / "
        "Coordinator) и итоговый exit_reason + PnL.\n\n"
        "Твоя задача — определить **главную** причину убытка из 10 категорий:\n"
        "1. signal_wrong — Layer 2 сигнал был ложным с самого начала\n"
        "2. sentiment_wrong — sentiment indicator оказался не предсказательным\n"
        "3. market_regime_changed — на момент входа было OK, regime сменился\n"
        "4. slippage_high — execution price отклонился от expected на >2bps\n"
        "5. risk_overlooked — субагенты пропустили red flag (correlation, low liq и пр.)\n"
        "6. execution_late — задержка между сигналом и ордером > 10 сек\n"
        "7. tp_too_aggressive — цена дошла до 80% TP, но развернулась\n"
        "8. sl_too_tight — стоп выбило, после чего цена пошла в нашу сторону\n"
        "9. correlation_overlooked — открыли коррелированную позицию\n"
        "10. macro_event_missed — торговали против важного macro-события\n\n"
        "Ответ строго JSON, без natural-language вне JSON. Не выдумывай "
        "категории — используй только перечисленные."
    )

    user_prompt_template = (
        "Trade {trade_id} ({side} {symbol}):\n"
        "Entry={entry_price}, Exit={exit_price}, PnL%={pnl_pct}, "
        "exit_reason={exit_reason}, holding={holding_time_min}min\n\n"
        "Signal: {signal_json}\n"
        "Market analyst: {market_json}\n"
        "Sentiment analyst: {sentiment_json}\n"
        "Risk overseer: {risk_json}\n"
        "Macro analyst: {macro_json}\n"
        "Coordinator: {coordinator_json}\n\n"
        "Output JSON:\n"
        '{{"primary_category": "...", "secondary_categories": [...], '
        '"what_went_wrong": "...", "what_we_should_have_seen": "...", '
        '"confidence_in_diagnosis": 0.0}}'
    )

    required_response_keys = (
        "primary_category",
        "secondary_categories",
        "what_went_wrong",
        "what_we_should_have_seen",
        "confidence_in_diagnosis",
    )

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        super()._validate_payload(payload)

        primary = payload.get("primary_category")
        if primary not in _MISTAKE_CATEGORIES:
            raise AgentExecutionError(
                f"mistake_classifier: invalid primary_category '{primary}', "
                f"expected one of {sorted(_MISTAKE_CATEGORIES)}"
            )

        secondary = payload.get("secondary_categories")
        if not isinstance(secondary, list):
            raise AgentExecutionError(
                f"mistake_classifier: secondary_categories must be list, "
                f"got {type(secondary).__name__}"
            )
        for item in secondary:
            if item not in _MISTAKE_CATEGORIES:
                raise AgentExecutionError(
                    f"mistake_classifier: invalid secondary_category '{item}'"
                )

        confidence = payload.get("confidence_in_diagnosis")
        if not isinstance(confidence, int | float):
            raise AgentExecutionError(
                f"mistake_classifier: confidence_in_diagnosis must be number, "
                f"got {type(confidence).__name__}"
            )
        if not 0.0 <= float(confidence) <= 1.0:
            raise AgentExecutionError(
                f"mistake_classifier: confidence_in_diagnosis must be in [0, 1], got {confidence}"
            )


def trade_outcome_to_context(outcome: TradeOutcome) -> dict[str, Any]:
    """Сериализация TradeOutcome → context dict для MistakeClassifierAgent.

    Caller (offline процесс) вызывает это для каждой убыточной сделки и
    передаёт результат в ``AgentRequest(context=...)``.
    """
    if not outcome.is_closed:
        raise ValueError(f"trade_outcome_to_context: outcome {outcome.trade_id} ещё открыт")
    return {
        "trade_id": outcome.trade_id,
        "symbol": outcome.symbol,
        "side": outcome.side,
        "entry_price": str(outcome.entry_price),
        "exit_price": str(outcome.exit_price),
        "pnl_pct": str(outcome.pnl_pct),
        "exit_reason": outcome.exit_reason or "UNKNOWN",
        "holding_time_min": outcome.holding_time_min if outcome.holding_time_min is not None else 0,
        "signal_json": outcome.signal_candidate_json,
        "market_json": outcome.market_analyst_json,
        "sentiment_json": outcome.sentiment_analyst_json,
        "risk_json": outcome.risk_overseer_json,
        "macro_json": outcome.macro_analyst_json,
        "coordinator_json": outcome.coordinator_json,
    }
