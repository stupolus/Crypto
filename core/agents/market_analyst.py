"""Market Analyst — quant-аналитик технической картины (план #17 §3.1).

Модель: Sonnet 4.6 (~$0.03/call). Вызывается на каждый firing-сигнал
Layer 2 чтобы дать LLM-оценку текущего market state перед передачей
в Coordinator.
"""

from __future__ import annotations

from typing import Any

from core.agents.anthropic import AnthropicAgent
from core.agents.base import AgentExecutionError

_MARKET_STATES = {
    "TRENDING_UP",
    "TRENDING_DOWN",
    "RANGE_BOUND",
    "VOLATILE_NO_TREND",
    "BREAKOUT_PENDING",
    "BREAKDOWN_PENDING",
    "POST_BREAKOUT_FATIGUE",
}

_VOLATILITY_LEVELS = {"low", "normal", "high"}
_LIQUIDITY_LEVELS = {"normal", "thin", "ample"}


class MarketAnalystAgent(AnthropicAgent):
    """Quant-аналитик технической картины.

    Контекст для ``user_prompt_template`` (обязательные ключи):
    - ``symbol`` — например "BTC-USDT"
    - ``timeframe`` — например "15m"
    - ``ohlcv_json`` — JSON с последними N свечами
    - ``atr``, ``donchian_high``, ``donchian_low``, ``ema20``, ``ema50``
    - ``orderbook_imbalance``, ``bid_5``, ``ask_5``
    - ``funding_rate``, ``oi_change_24h_pct``

    Output JSON keys:
    - ``state`` (один из 7 market states)
    - ``key_levels`` ({"support": [...], "resistance": [...]})
    - ``volatility`` (low/normal/high)
    - ``liquidity`` (normal/thin/ample)
    - ``notes`` (1-2 строки natural language)
    """

    name = "market_analyst"
    model = "claude-sonnet-4-6"
    max_tokens = 1024

    system_prompt = (
        "Ты — quant-аналитик хедж-фонда с 10 годами опыта на crypto-перпах. "
        "Анализируешь техническую картину одного символа на одном таймфрейме. "
        "Твоя задача — определить market state объективно по данным, "
        "БЕЗ предсказания будущей цены. Только текущий regime.\n\n"
        "Возможные states:\n"
        "- TRENDING_UP / TRENDING_DOWN — устойчивый направленный тренд\n"
        "- RANGE_BOUND — цена в горизонтальном диапазоне\n"
        "- VOLATILE_NO_TREND — высокая волатильность, направление не ясно\n"
        "- BREAKOUT_PENDING — цена давит в верх диапазона, может пробить\n"
        "- BREAKDOWN_PENDING — то же вниз\n"
        "- POST_BREAKOUT_FATIGUE — был пробой, сейчас силы кончились\n\n"
        "Ответ строго JSON, без natural-language вне JSON."
    )

    user_prompt_template = (
        "Symbol: {symbol}\n"
        "Timeframe: {timeframe}\n"
        "Candles (recent N): {ohlcv_json}\n"
        "Indicators: ATR={atr}, Donchian high/low={donchian_high}/{donchian_low}, "
        "EMA20={ema20}, EMA50={ema50}\n"
        "Orderbook: bid_5={bid_5}, ask_5={ask_5}, imbalance={orderbook_imbalance}\n"
        "Funding: {funding_rate}, OI 24h change: {oi_change_24h_pct}\n\n"
        "Output JSON:\n"
        '{{"state": "...", "key_levels": {{"support": [...], "resistance": [...]}}, '
        '"volatility": "...", "liquidity": "...", "notes": "..."}}'
    )

    required_response_keys = ("state", "key_levels", "volatility", "liquidity", "notes")

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        super()._validate_payload(payload)

        state = payload.get("state")
        if state not in _MARKET_STATES:
            raise AgentExecutionError(
                f"market_analyst: invalid state '{state}', expected one of {sorted(_MARKET_STATES)}"
            )

        volatility = payload.get("volatility")
        if volatility not in _VOLATILITY_LEVELS:
            raise AgentExecutionError(
                f"market_analyst: invalid volatility '{volatility}', "
                f"expected one of {sorted(_VOLATILITY_LEVELS)}"
            )

        liquidity = payload.get("liquidity")
        if liquidity not in _LIQUIDITY_LEVELS:
            raise AgentExecutionError(
                f"market_analyst: invalid liquidity '{liquidity}', "
                f"expected one of {sorted(_LIQUIDITY_LEVELS)}"
            )

        key_levels = payload.get("key_levels")
        if not isinstance(key_levels, dict):
            raise AgentExecutionError(
                f"market_analyst: key_levels must be dict, got {type(key_levels).__name__}"
            )
        for k in ("support", "resistance"):
            if k not in key_levels:
                raise AgentExecutionError(f"market_analyst: key_levels missing '{k}'")
            if not isinstance(key_levels[k], list):
                raise AgentExecutionError(
                    f"market_analyst: key_levels.{k} must be list, "
                    f"got {type(key_levels[k]).__name__}"
                )
