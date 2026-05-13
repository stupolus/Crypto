"""Risk Overseer — единственный subagent с veto power (план #17 §3.3).

Модель: Opus 4.7 (~$0.10/call). Критичный субагент. Его задача —
**НЕ зарабатывать, а защищать капитал**. Он критически оценивает
предложенную сделку с учётом portfolio state, recent trades, daily PnL,
correlation, black swan событий.

Veto rule: если Risk Overseer сказал ``approved=False`` — Coordinator
возвращает HOLD независимо от других субагентов.

Также может ограничить ``max_risk_pct`` (cap размера сделки).
"""

from __future__ import annotations

from typing import Any

from core.agents.anthropic import AnthropicAgent
from core.agents.base import AgentExecutionError


class RiskOverseerAgent(AnthropicAgent):
    """Chief Risk Officer субагент.

    Контекст для ``user_prompt_template``:
    - ``trade_proposal_json`` — proposed trade (символ, направление, размер)
    - ``equity`` — текущий equity
    - ``open_positions_json`` — список открытых позиций
    - ``daily_pnl`` — текущий PnL за день (%)
    - ``recent_trades_json`` — последние 10 сделок
    - ``correlation_json`` — матрица корреляций между символами

    Output:
    - ``approved`` (bool) — главное решение
    - ``max_risk_pct`` (float, 0..2.0) — cap на размер риска
    - ``reasoning`` (string) — почему такое решение
    - ``concerns`` (list of strings) — что насторожило
    - ``confidence`` (float, 0..1)
    """

    name = "risk_overseer"
    model = "claude-opus-4-7"
    max_tokens = 1024

    system_prompt = (
        "Ты — Chief Risk Officer хедж-фонда. Твоя задача — "
        "**НЕ зарабатывать, а защищать капитал**.\n\n"
        "Критически оцениваешь предложенную сделку. Учитываешь:\n"
        "1. Не повторяем ли мы недавние ошибки (recent_trades)\n"
        "2. Корреляция с открытыми позициями\n"
        "3. Не превышаем ли daily/weekly limits\n"
        "4. Sanity check: разумна entry vs current price?\n"
        "5. Black swan чек: торгуем во время известных high-impact событий?\n"
        "6. Антипаттерны: НИКОГДА не одобрять hedge той же монеты "
        "(см. правило бизнес/правила-торговли/анти-хедж-той-же-монеты)\n\n"
        "Имеешь veto power. Лучше пропустить хорошую сделку чем взять плохую.\n"
        "По умолчанию **скептичен** — для approve нужны явные аргументы.\n\n"
        "Ответ строго JSON, без natural-language вне JSON."
    )

    user_prompt_template = (
        "Trade proposal: {trade_proposal_json}\n\n"
        "Portfolio state:\n"
        "- Equity: {equity}\n"
        "- Open positions: {open_positions_json}\n"
        "- Daily PnL: {daily_pnl}\n"
        "- Recent trades (last 10): {recent_trades_json}\n"
        "- Correlation matrix: {correlation_json}\n\n"
        "Output JSON:\n"
        '{{"approved": true|false, "max_risk_pct": 0..2.0, '
        '"reasoning": "...", "concerns": [...], "confidence": 0..1}}'
    )

    required_response_keys = ("approved", "max_risk_pct", "reasoning", "concerns", "confidence")

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        super()._validate_payload(payload)

        approved = payload.get("approved")
        if not isinstance(approved, bool):
            raise AgentExecutionError(
                f"risk_overseer: approved must be bool, got {type(approved).__name__}"
            )

        max_risk = payload.get("max_risk_pct")
        if not isinstance(max_risk, int | float):
            raise AgentExecutionError(
                f"risk_overseer: max_risk_pct must be number, got {type(max_risk).__name__}"
            )
        if not 0.0 <= float(max_risk) <= 2.0:
            raise AgentExecutionError(
                f"risk_overseer: max_risk_pct={max_risk} out of range [0, 2.0]"
            )

        confidence = payload.get("confidence")
        if not isinstance(confidence, int | float):
            raise AgentExecutionError(
                f"risk_overseer: confidence must be number, got {type(confidence).__name__}"
            )
        if not 0.0 <= float(confidence) <= 1.0:
            raise AgentExecutionError(f"risk_overseer: confidence={confidence} out of range [0, 1]")

        reasoning = payload.get("reasoning")
        if not isinstance(reasoning, str) or not reasoning.strip():
            raise AgentExecutionError("risk_overseer: reasoning must be non-empty string")

        concerns = payload.get("concerns")
        if not isinstance(concerns, list):
            raise AgentExecutionError(
                f"risk_overseer: concerns must be list, got {type(concerns).__name__}"
            )
        if not all(isinstance(x, str) for x in concerns):
            raise AgentExecutionError("risk_overseer: concerns must contain only strings")
