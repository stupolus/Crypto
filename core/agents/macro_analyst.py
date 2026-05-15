"""Macro Analyst — market regime classifier (план #17 §3.5).

Модель: Sonnet 4.6 (~$0.04/call). Вызывается раз в час (а не на каждый
сигнал) — macro context медленно меняется. Результат кешируется и
подаётся всем hot-loop subagent'ам.

Определяет market regime который влияет на агрессивность всех решений:
- RISK_ON — стандартное поведение, можно лонгить
- NEUTRAL — без изменений
- RISK_OFF — Risk Overseer должен быть жёстче, possible portfolio hedge
- CRISIS — отменяем все лонги, только короткие или закрытие

См. MacroSnapshot из parsers.macro.models — вход для этого агента.
"""

from __future__ import annotations

from typing import Any

from core.agents.anthropic import AnthropicAgent
from core.agents.base import AgentExecutionError

_REGIMES = {"RISK_ON", "NEUTRAL", "RISK_OFF", "CRISIS"}


class MacroAnalystAgent(AnthropicAgent):
    """Macro strategist — определяет market regime для всего портфеля.

    Контекст для ``user_prompt_template``:
    - ``dxy``, ``dxy_change_24h_pct`` — US Dollar Index + 24h дельта
    - ``vix``, ``vix_change_24h_pct`` — S&P volatility
    - ``spx``, ``ndx`` — S&P 500 / NASDAQ-100
    - ``gold``, ``oil`` — commodities
    - ``yield_10y`` — 10-year Treasury yield
    - ``btc_dominance_pct`` — % крипто-рынка в BTC
    - ``fed_calendar`` — JSON ближайших FOMC/rate-decision дат
    - ``earnings_schedule`` — mega-cap tech earnings dates

    Output:
    - ``regime`` (RISK_ON / NEUTRAL / RISK_OFF / CRISIS)
    - ``confidence`` (0..1)
    - ``rationale`` (string)
    - ``portfolio_hedge_recommended`` (bool)
    - ``hedge_size_pct_of_long_exposure`` (0..50)
    - ``risk_off_drivers`` (list of strings)
    - ``duration_estimate_hours`` (int)
    """

    name = "macro_analyst"
    model = "claude-sonnet-4-6"
    max_tokens = 1024

    system_prompt = (
        "Ты — macro strategist хедж-фонда. Анализируешь НЕ отдельную сделку, "
        "а **режим всего рынка** для crypto-портфеля.\n\n"
        "Crypto коррелирует с risk-on/risk-off режимом TradFi. Когда DXY rocket "
        "+ VIX spike + NDX dump — это RISK_OFF, наши crypto-лонги под давлением. "
        "На CRISIS — выходим во всё.\n\n"
        "Возможные regimes:\n"
        "- RISK_ON — все системы зелёные, можно нормально лонгить\n"
        "- NEUTRAL — без изменений\n"
        "- RISK_OFF — нужно быть осторожнее, possible portfolio hedge\n"
        "- CRISIS — отменяем все лонги, только короткие/exit\n\n"
        "Если portfolio_hedge_recommended=true — Portfolio Hedger откроет "
        "SHORT BTC/ETH размером hedge_size_pct_of_long_exposure% от лонг-экспозиции.\n\n"
        "Ответ строго JSON, без natural-language вне JSON."
    )

    user_prompt_template = (
        "Macro snapshot (24h window):\n"
        "- DXY: {dxy}, change={dxy_change_24h_pct}%\n"
        "- VIX: {vix}, change={vix_change_24h_pct}%\n"
        "- S&P futures: {spx}, NDX: {ndx}\n"
        "- Gold: {gold}, Oil: {oil}\n"
        "- 10Y yield: {yield_10y}\n"
        "- BTC dominance: {btc_dominance_pct}%\n"
        "- FED upcoming 7d: {fed_calendar}\n"
        "- Earnings schedule (mega-cap tech): {earnings_schedule}\n\n"
        "Output JSON:\n"
        '{{"regime": "...", "confidence": 0..1, "rationale": "...", '
        '"portfolio_hedge_recommended": true|false, '
        '"hedge_size_pct_of_long_exposure": 0..50, '
        '"risk_off_drivers": [...], "duration_estimate_hours": ...}}'
    )

    required_response_keys = (
        "regime",
        "confidence",
        "rationale",
        "portfolio_hedge_recommended",
        "hedge_size_pct_of_long_exposure",
        "risk_off_drivers",
        "duration_estimate_hours",
    )

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        super()._validate_payload(payload)

        regime = payload.get("regime")
        if regime not in _REGIMES:
            raise AgentExecutionError(
                f"macro_analyst: invalid regime '{regime}', expected one of {sorted(_REGIMES)}"
            )

        confidence = payload.get("confidence")
        if not isinstance(confidence, int | float) or not 0.0 <= float(confidence) <= 1.0:
            raise AgentExecutionError(
                f"macro_analyst: confidence={confidence} must be number in [0, 1]"
            )

        rationale = payload.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise AgentExecutionError("macro_analyst: rationale must be non-empty string")

        hedge_rec = payload.get("portfolio_hedge_recommended")
        if not isinstance(hedge_rec, bool):
            raise AgentExecutionError(
                f"macro_analyst: portfolio_hedge_recommended must be bool, "
                f"got {type(hedge_rec).__name__}"
            )

        hedge_size = payload.get("hedge_size_pct_of_long_exposure")
        if not isinstance(hedge_size, int | float) or not 0.0 <= float(hedge_size) <= 50.0:
            raise AgentExecutionError(
                f"macro_analyst: hedge_size_pct_of_long_exposure={hedge_size} "
                f"must be number in [0, 50]"
            )

        drivers = payload.get("risk_off_drivers")
        if not isinstance(drivers, list):
            raise AgentExecutionError(
                f"macro_analyst: risk_off_drivers must be list, got {type(drivers).__name__}"
            )
        if not all(isinstance(x, str) for x in drivers):
            raise AgentExecutionError("macro_analyst: risk_off_drivers must contain only strings")

        duration = payload.get("duration_estimate_hours")
        if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0:
            raise AgentExecutionError(
                f"macro_analyst: duration_estimate_hours={duration} must be non-negative int"
            )
