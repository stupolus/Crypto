"""AgentTeam — оркестратор Layer 3 (план #17 §3 + §6).

Координирует вызовы 5 субагентов на firing-сигнал Layer 2:
1. Macro Analyst (кешируется на 1 час, не зовётся на каждый сигнал)
2. Параллельно: Market Analyst + Sentiment Analyst + Risk Overseer
3. Coordinator получает все 4 ответа → синтез TradeProposal

Использование DI: каждый агент передаётся в конструктор. Это позволяет:
- Подменять MockAgent в тестах без реальных API-вызовов
- Использовать разные модели на разных стадиях (паудры на debug)
- Имплементировать circuit breaker (если Anthropic API down → fallback)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from core.agents.base import AgentError, AgentExecutionError, AgentRequest, BaseAgent

logger = logging.getLogger(__name__)

# Если macro_snapshot старше этого — не reuse, считаем заново.
_MACRO_CACHE_TTL_S = 3600.0


@dataclass(frozen=True)
class TeamDecision:
    """Финальный output AgentTeam — то что отдаётся в Layer 4 (Risk Engine).

    ``coordinator_payload`` содержит финальный TradeProposal с action/size/etc.
    Остальные поля — для аудита и debug.
    """

    coordinator_payload: dict[str, Any]
    subagent_payloads: dict[str, dict[str, Any]]
    macro_cached: bool
    total_latency_ms: int
    total_cost_usd: float
    errors: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class _MacroCacheEntry:
    payload: dict[str, Any]
    fetched_at_ts: float


class AgentTeam:
    """Оркестратор 5 субагентов плана #17.

    Жизненный цикл:
    1. Конструируется один раз с DI всех 5 агентов
    2. На каждый firing-сигнал — ``await team.evaluate_signal(...)``
    3. Macro кешируется (на час), остальные параллельно
    4. Возвращает TeamDecision

    Errors handling:
    - Risk Overseer fail → возвращаем HOLD с reason="risk_overseer down"
      (защитный default — без RO не можем approve)
    - Market/Sentiment/Macro fail → продолжаем, но composite_confidence ↓
    - Coordinator fail → возвращаем HOLD с error details
    """

    def __init__(
        self,
        *,
        market_analyst: BaseAgent,
        sentiment_analyst: BaseAgent,
        risk_overseer: BaseAgent,
        macro_analyst: BaseAgent,
        coordinator: BaseAgent,
        macro_cache_ttl_s: float = _MACRO_CACHE_TTL_S,
    ) -> None:
        self._market = market_analyst
        self._sentiment = sentiment_analyst
        self._risk = risk_overseer
        self._macro = macro_analyst
        self._coordinator = coordinator
        self._macro_cache: _MacroCacheEntry | None = None
        self._macro_cache_ttl_s = macro_cache_ttl_s

    async def _get_macro_snapshot(
        self, macro_context: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        """Returns (payload, was_cached)."""
        now = time.monotonic()
        if (
            self._macro_cache is not None
            and now - self._macro_cache.fetched_at_ts < self._macro_cache_ttl_s
        ):
            return self._macro_cache.payload, True
        try:
            resp = await self._macro.run(AgentRequest(context=macro_context))
        except AgentError as e:
            logger.warning("macro_analyst failed, using empty fallback: %s", e)
            return {"regime": "NEUTRAL", "confidence": 0.0}, False
        self._macro_cache = _MacroCacheEntry(payload=resp.payload, fetched_at_ts=now)
        return resp.payload, False

    async def _run_safe(
        self, agent: BaseAgent, ctx: dict[str, Any], errors: list[str]
    ) -> dict[str, Any] | None:
        """Запускает агента, логирует ошибки в общий список."""
        try:
            resp = await agent.run(AgentRequest(context=ctx))
        except AgentError as e:
            errors.append(f"{agent.name}: {e}")
            return None
        return resp.payload

    async def evaluate_signal(
        self,
        *,
        signal_context: dict[str, Any],
        market_context: dict[str, Any],
        sentiment_context: dict[str, Any],
        risk_context: dict[str, Any],
        macro_context: dict[str, Any],
        past_mistakes: str = "",
    ) -> TeamDecision:
        """Главная точка входа. Возвращает TeamDecision с финальным action.

        ``signal_context`` — оригинальный SignalCandidate от Layer 2.
        Остальные contexts — input для соответствующих субагентов.

        ``past_mistakes`` — Layer 6 текстовое summary похожих past mistakes
        (опционально, default ""). Передаётся в Coordinator prompt.

        Если Risk Overseer упал — возвращаем HOLD автоматически (safety).
        """
        t_start = time.monotonic()
        errors: list[str] = []

        # 1. Macro (cached) — может вернуть fallback при ошибке
        macro_payload, macro_was_cached = await self._get_macro_snapshot(macro_context)

        # 2. Параллельно: Market, Sentiment, Risk Overseer
        market_task = self._run_safe(self._market, market_context, errors)
        sentiment_task = self._run_safe(self._sentiment, sentiment_context, errors)
        risk_task = self._run_safe(self._risk, risk_context, errors)
        market_payload, sentiment_payload, risk_payload = await asyncio.gather(
            market_task, sentiment_task, risk_task
        )

        # 3. Risk Overseer down → safety HOLD (не пытаемся Coordinator вызвать)
        if risk_payload is None:
            return TeamDecision(
                coordinator_payload={
                    "action": "HOLD",
                    "size_risk_pct": 0.0,
                    "entry_price": None,
                    "sl_price": None,
                    "tp_prices": [],
                    "reasoning": "Risk Overseer недоступен — defensively HOLD",
                    "composite_confidence": 0.0,
                },
                subagent_payloads={
                    "macro": macro_payload,
                    "market": market_payload or {},
                    "sentiment": sentiment_payload or {},
                    "risk": {},
                },
                macro_cached=macro_was_cached,
                total_latency_ms=int((time.monotonic() - t_start) * 1000),
                total_cost_usd=0.0,
                errors=tuple(errors),
            )

        # 4. Coordinator получает всё + Layer 6 past_mistakes (default "")
        coordinator_context = {
            "signal_json": _safe_json_dumps(signal_context),
            "market_analyst_json": _safe_json_dumps(market_payload or {}),
            "sentiment_analyst_json": _safe_json_dumps(sentiment_payload or {}),
            "risk_overseer_json": _safe_json_dumps(risk_payload),
            "macro_analyst_json": _safe_json_dumps(macro_payload),
            "past_mistakes": past_mistakes,
        }
        try:
            coordinator_resp = await self._coordinator.run(
                AgentRequest(context=coordinator_context)
            )
            coordinator_payload = coordinator_resp.payload
        except AgentExecutionError as e:
            errors.append(f"coordinator: {e}")
            coordinator_payload = {
                "action": "HOLD",
                "size_risk_pct": 0.0,
                "entry_price": None,
                "sl_price": None,
                "tp_prices": [],
                "reasoning": f"Coordinator failed: {e}",
                "composite_confidence": 0.0,
            }

        return TeamDecision(
            coordinator_payload=coordinator_payload,
            subagent_payloads={
                "macro": macro_payload,
                "market": market_payload or {},
                "sentiment": sentiment_payload or {},
                "risk": risk_payload,
            },
            macro_cached=macro_was_cached,
            total_latency_ms=int((time.monotonic() - t_start) * 1000),
            total_cost_usd=0.0,  # TODO: aggregate cost из всех subagent.tokens_in/out
            errors=tuple(errors),
        )


def _safe_json_dumps(obj: Any) -> str:
    """Сериализует dict в JSON-строку для подачи в промпт другого агента."""
    import json

    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(obj)
