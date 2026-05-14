"""LLM Gate — финальный фильтр перед отправкой OrderRequest в Risk Engine.

Принимает OrderRequest от Layer 2 стратегии, прогоняет через AgentTeam
(Layer 3), и возвращает либо модифицированный OrderRequest (с entry/SL/TP
от Coordinator'а), либо None (veto / HOLD).

Использование в runner::

    order_request = strategy.on_candle_close(ctx)
    if order_request is None:
        return  # стратегия не сработала

    result = await llm_gate(
        team=agent_team,
        order_request=order_request,
        strategy_name="btc_breakout",
        timestamp_ms=int(time.time() * 1000),
        indicators={"atr": "100.5", ...},
        confidence_raw=0.7,
        state=state_snapshot,
        market_data=...,
        sentiment_data=...,
        macro_data=...,
    )
    if result.approved_request is None:
        logger.info("LLM gate veto: %s", result.decision.coordinator_payload)
        return
    await place_order(result.approved_request)

Семантика финального действия:

- ``HOLD`` → ``approved_request=None`` (veto)
- ``BUY/SELL`` ≠ original side → ``approved_request=None``
  (защита от того что Coordinator случайно перевернул сделку)
- ``BUY/SELL`` == original side → ``approved_request`` = OrderRequest с
  entry/SL/TP пересчитанными по Coordinator payload (если они там есть)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from adapters.bingx.private_models import OrderRequest
from core.agents.evaluate import (
    MacroContextData,
    MarketContextData,
    RunnerStateSnapshot,
    SentimentContextData,
    evaluate_with_team,
)
from core.agents.order_request_bridge import build_signal_candidate
from core.agents.team import AgentTeam, TeamDecision

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMGateResult:
    """Результат прогонки OrderRequest через AgentTeam.

    Если ``approved_request is None`` — runner НЕ должен размещать ордер.
    Причина (HOLD / side mismatch / veto) логируется в ``reason`` и доступна
    через ``decision`` для аудита.
    """

    approved_request: OrderRequest | None
    decision: TeamDecision
    reason: str


async def llm_gate(
    *,
    team: AgentTeam,
    order_request: OrderRequest,
    strategy_name: str,
    timestamp_ms: int,
    indicators: dict[str, Any] | None,
    confidence_raw: float,
    state: RunnerStateSnapshot,
    market_data: MarketContextData,
    sentiment_data: SentimentContextData,
    macro_data: MacroContextData,
    past_mistakes: str = "",
) -> LLMGateResult:
    """Прогонка OrderRequest через AgentTeam с возможной модификацией SL/TP.

    Coordinator возвращает либо HOLD (veto), либо BUY/SELL с уточнённым
    entry/SL/TP. Если Coordinator меняет сторону (BUY→SELL или наоборот) —
    это считаем veto: стратегия предложила одно, Coordinator другое; вместо
    того чтобы выполнять противоположную сделку — отказываемся, лог критич.

    ``past_mistakes`` — Layer 6 textual summary похожих past mistakes
    (опционально). Передаётся в Coordinator prompt.
    """
    signal = build_signal_candidate(
        order_request,
        strategy_name=strategy_name,
        timestamp_ms=timestamp_ms,
        indicators=indicators,
        confidence_raw=confidence_raw,
    )
    decision = await evaluate_with_team(
        team,
        signal,
        state,
        market_data=market_data,
        sentiment_data=sentiment_data,
        macro_data=macro_data,
        past_mistakes=past_mistakes,
    )
    payload = decision.coordinator_payload
    action = payload.get("action")

    if action == "HOLD":
        logger.info(
            "llm_gate HOLD: %s | reasoning=%s",
            order_request.symbol,
            payload.get("reasoning", "<none>"),
        )
        return LLMGateResult(
            approved_request=None,
            decision=decision,
            reason="HOLD",
        )

    if action not in ("BUY", "SELL"):
        logger.warning(
            "llm_gate: unexpected action %r — treating as veto",
            action,
        )
        return LLMGateResult(
            approved_request=None,
            decision=decision,
            reason=f"unexpected_action:{action!r}",
        )

    if action != order_request.side:
        logger.warning(
            "llm_gate side mismatch: strategy=%s coordinator=%s — veto",
            order_request.side,
            action,
        )
        return LLMGateResult(
            approved_request=None,
            decision=decision,
            reason=f"side_mismatch:{order_request.side}->{action}",
        )

    updates = _build_request_updates(order_request, payload)
    approved = order_request.model_copy(update=updates) if updates else order_request
    return LLMGateResult(
        approved_request=approved,
        decision=decision,
        reason="APPROVED",
    )


def _build_request_updates(order_request: OrderRequest, payload: dict[str, Any]) -> dict[str, Any]:
    """Извлечь entry/SL/TP из coordinator_payload и собрать update-dict.

    Возвращает пустой dict если в payload ничего полезного нет — runner
    использует исходный OrderRequest. Невалидные значения (не Decimal,
    ≤ 0) игнорируются с warning.
    """
    updates: dict[str, Any] = {}

    sl_price = _coerce_decimal(payload.get("sl_price"))
    if sl_price is not None and sl_price != order_request.attached_stop_loss:
        updates["attached_stop_loss"] = sl_price

    tp_prices = payload.get("tp_prices")
    if isinstance(tp_prices, list) and tp_prices:
        tp = _coerce_decimal(tp_prices[0])
        if tp is not None and tp != order_request.attached_take_profit:
            updates["attached_take_profit"] = tp

    if order_request.order_type == "LIMIT":
        entry = _coerce_decimal(payload.get("entry_price"))
        if entry is not None and entry != order_request.price:
            updates["price"] = entry

    return updates


def _coerce_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        logger.warning("llm_gate: cannot parse %r as Decimal", value)
        return None
    if result <= 0:
        logger.warning("llm_gate: non-positive price %s — ignoring", result)
        return None
    return result
