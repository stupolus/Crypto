"""Coordinator — синтезатор всех subagent'ов (план #17 §3.7).

Модель: Opus 4.7 (~$0.08/call). Получает результаты Market + Sentiment +
Risk Overseer + Macro и синтезирует финальное TradeProposal.

Жёсткие правила:
1. Если Risk Overseer сказал approved=False → action="HOLD"
2. Если composite confidence < 0.6 → action="HOLD"
3. size_risk_pct ≤ Risk Overseer's max_risk_pct (cap не превышаем)
4. Если Sentiment сильно negative + Market в BREAKDOWN_PENDING → caution++
5. Layer 6 past_mistakes (если переданы) — учитываем при corruption
   confidence: много recent SL'ков на символе → ослабить confidence.
"""

from __future__ import annotations

from typing import Any

from core.agents.anthropic import AnthropicAgent
from core.agents.base import AgentExecutionError

_ACTIONS = {"BUY", "SELL", "HOLD"}


class CoordinatorAgent(AnthropicAgent):
    """Финальный synthesizer перед Layer 4 Risk Engine.

    Контекст для ``user_prompt_template``:
    - ``signal_json`` — оригинальный SignalCandidate
    - ``market_analyst_json`` — ответ Market Analyst
    - ``sentiment_analyst_json`` — ответ Sentiment Analyst
    - ``risk_overseer_json`` — ответ Risk Overseer (с veto)
    - ``macro_analyst_json`` — ответ Macro Analyst
    - ``past_mistakes`` — Layer 6 текстовое summary похожих past mistakes
      (опционально, default "")

    Output:
    - ``action`` (BUY/SELL/HOLD)
    - ``size_risk_pct`` (0..2.0, ≤ Risk Overseer max_risk_pct)
    - ``entry_price`` (Decimal-string)
    - ``sl_price`` (Decimal-string)
    - ``tp_prices`` (list of Decimal-strings, обычно 1-2 уровня)
    - ``reasoning`` (string, на русском для journal + Telegram)
    - ``composite_confidence`` (0..1)
    """

    name = "coordinator"
    model = "claude-opus-4-7"
    max_tokens = 1024

    system_prompt = (
        "Ты — Coordinator торгового бота. Получаешь мнения 4 субагентов "
        "и **синтезируешь финальное решение**: BUY / SELL / HOLD.\n\n"
        "ЖЁСТКИЕ ПРАВИЛА:\n"
        "1. Если Risk Overseer сказал approved=false → action='HOLD' (veto)\n"
        "2. composite_confidence = взвешенное среднее всех confidences "
        "(Risk Overseer вес 2x)\n"
        "3. Если composite_confidence < 0.6 → action='HOLD'\n"
        "4. size_risk_pct НЕ превышает Risk Overseer max_risk_pct\n"
        "5. На RISK_OFF / CRISIS regime от Macro Analyst — снижай агрессивность\n"
        "6. Если Sentiment < -0.5 + Market в BREAKDOWN_PENDING — caution++\n"
        "7. Past mistakes (Layer 6): если на этом символе уже было 2+ SL за "
        "последнее время — ослабь composite_confidence на 0.1, и если "
        "получается < 0.6 — переключи action на HOLD. Если past_mistakes "
        "пустое — это поле игнорируй.\n\n"
        "reasoning — на **русском**, 1-3 предложения. Будет в journal и Telegram.\n\n"
        "Ответ строго JSON, без natural-language вне JSON."
    )

    user_prompt_template = (
        "Original signal: {signal_json}\n\n"
        "Subagent outputs:\n"
        "Market Analyst: {market_analyst_json}\n"
        "Sentiment Analyst: {sentiment_analyst_json}\n"
        "Risk Overseer: {risk_overseer_json}\n"
        "Macro Analyst: {macro_analyst_json}\n\n"
        "Past mistakes context (Layer 6 — may be empty):\n"
        "{past_mistakes}\n\n"
        "Output JSON:\n"
        '{{"action": "BUY|SELL|HOLD", "size_risk_pct": 0..2.0, '
        '"entry_price": "...", "sl_price": "...", "tp_prices": [...], '
        '"reasoning": "...", "composite_confidence": 0..1}}'
    )

    required_response_keys = (
        "action",
        "size_risk_pct",
        "entry_price",
        "sl_price",
        "tp_prices",
        "reasoning",
        "composite_confidence",
    )

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        super()._validate_payload(payload)

        action = payload.get("action")
        if action not in _ACTIONS:
            raise AgentExecutionError(
                f"coordinator: invalid action '{action}', expected one of {sorted(_ACTIONS)}"
            )

        size = payload.get("size_risk_pct")
        if not isinstance(size, int | float) or not 0.0 <= float(size) <= 2.0:
            raise AgentExecutionError(
                f"coordinator: size_risk_pct={size} must be number in [0, 2.0]"
            )

        confidence = payload.get("composite_confidence")
        if not isinstance(confidence, int | float) or not 0.0 <= float(confidence) <= 1.0:
            raise AgentExecutionError(
                f"coordinator: composite_confidence={confidence} must be number in [0, 1]"
            )

        # Для HOLD entry/sl/tp могут быть null/нерелевантны.
        # Для BUY/SELL — должны быть строки.
        if action in {"BUY", "SELL"}:
            for key in ("entry_price", "sl_price"):
                value = payload.get(key)
                if not isinstance(value, str) or not value.strip():
                    raise AgentExecutionError(
                        f"coordinator: {key} required for action={action}, got {value!r}"
                    )

        tp_prices = payload.get("tp_prices")
        if not isinstance(tp_prices, list):
            raise AgentExecutionError(
                f"coordinator: tp_prices must be list, got {type(tp_prices).__name__}"
            )

        reasoning = payload.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            raise AgentExecutionError("coordinator: reasoning must be non-empty string")
