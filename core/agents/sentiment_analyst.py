"""Sentiment Analyst — классификатор настроения рынка (план #17 §3.2).

Модель: Haiku 4.5 (~$0.005/call) — дешёвый и быстрый, задача
классификационная (не reasoning-heavy).

Вход: Twitter snapshot (sentiment_score из Groq pre-processing) +
breaking news headlines + funding extremes + TG-channels агрегат.

Выход: единая оценка sentiment для конкретного символа.
"""

from __future__ import annotations

from typing import Any

from core.agents.anthropic import AnthropicAgent
from core.agents.base import AgentExecutionError


class SentimentAnalystAgent(AnthropicAgent):
    """Sentiment-классификатор для одного символа.

    Контекст для ``user_prompt_template``:
    - ``symbol`` — например "BTC-USDT"
    - ``twitter_sentiment_score`` — средний sentiment из Groq за последний час (-1..+1)
    - ``twitter_top_mentions`` — JSON списка топ-твитов с весом
    - ``news_headlines`` — JSON последних headlines с timestamp
    - ``funding_rate`` — текущий funding rate (%) — extreme = sentiment signal
    - ``tg_channels_summary`` — агрегат tg-каналов

    Output JSON keys:
    - ``sentiment_score`` (float, -1..+1)
    - ``key_events`` (list of strings — что сейчас драйвит)
    - ``risk_flags`` (list of strings — что может pump/dump)
    - ``confidence`` (float, 0..1)
    """

    name = "sentiment_analyst"
    model = "claude-haiku-4-5"
    max_tokens = 512

    system_prompt = (
        "Ты — sentiment-classifier для crypto. Задача узкая и быстрая: "
        "по агрегированным Twitter/news/funding данным выдать **число** "
        "от -1 (bearish) до +1 (bullish) для конкретного символа.\n\n"
        "НЕ делай рыночный прогноз. НЕ давай рекомендации long/short. "
        "Только классификация *настроения* в моменте.\n\n"
        "key_events — 1-3 коротких фразы что *сейчас* двигает sentiment. "
        "risk_flags — что может вызвать резкий pump/dump (Fed announce, "
        "earnings, etc).\n\n"
        "Ответ строго JSON, без natural-language вне JSON."
    )

    user_prompt_template = (
        "Symbol: {symbol}\n"
        "Twitter sentiment (Groq pre-processed): {twitter_sentiment_score}\n"
        "Top mentions: {twitter_top_mentions}\n"
        "News headlines: {news_headlines}\n"
        "Funding rate: {funding_rate}\n"
        "TG channels: {tg_channels_summary}\n\n"
        "Output JSON:\n"
        '{{"sentiment_score": -1..+1, "key_events": [...], '
        '"risk_flags": [...], "confidence": 0..1}}'
    )

    required_response_keys = ("sentiment_score", "key_events", "risk_flags", "confidence")

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        super()._validate_payload(payload)

        score = payload.get("sentiment_score")
        if not isinstance(score, int | float):
            raise AgentExecutionError(
                f"sentiment_analyst: sentiment_score must be number, got {type(score).__name__}"
            )
        if not -1.0 <= float(score) <= 1.0:
            raise AgentExecutionError(
                f"sentiment_analyst: sentiment_score={score} out of range [-1, 1]"
            )

        confidence = payload.get("confidence")
        if not isinstance(confidence, int | float):
            raise AgentExecutionError(
                f"sentiment_analyst: confidence must be number, got {type(confidence).__name__}"
            )
        if not 0.0 <= float(confidence) <= 1.0:
            raise AgentExecutionError(
                f"sentiment_analyst: confidence={confidence} out of range [0, 1]"
            )

        for field in ("key_events", "risk_flags"):
            value = payload.get(field)
            if not isinstance(value, list):
                raise AgentExecutionError(
                    f"sentiment_analyst: {field} must be list, got {type(value).__name__}"
                )
            if not all(isinstance(x, str) for x in value):
                raise AgentExecutionError(f"sentiment_analyst: {field} must contain only strings")
