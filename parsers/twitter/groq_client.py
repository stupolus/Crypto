"""Groq client — быстрая классификация Twitter/news через Llama 3.1.

Groq — inference платформа с очень быстрым output (~500 токенов/сек),
дешевле чем Claude (~$0.0001 per tweet). Используется как
pre-processor для Twitter pipeline:

  raw tweet → Groq Llama → JSON {sentiment, tokens, relevance}
       → aggregator → SentimentSnapshot → Sentiment Analyst Layer 3

Тарифы (2026): free tier даёт 30 req/min на Llama 3.1 70B — достаточно
для одного крипто-бота. Production: paid tier ~$0.59/M input tokens.

Использование::

    client = GroqClient(api_key="gsk-...", model="llama-3.1-70b-versatile")
    classification = await client.classify_tweet(tweet_text="...")
    # → {"sentiment": 0.5, "tokens": ["BTC"], "relevance": "high"}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "llama-3.1-70b-versatile"
_TIMEOUT_S = 15.0

_SYSTEM_PROMPT = (
    "You are a crypto sentiment classifier. Given a tweet text, output strict JSON:\n"
    '{"sentiment": -1.0..+1.0, "tokens": ["BTC", "ETH", ...], '
    '"relevance": "high"|"medium"|"low"|"noise", "is_breaking": bool, '
    '"summary": "one sentence"}\n\n'
    "- sentiment: -1=very bearish, 0=neutral, +1=very bullish\n"
    "- tokens: cryptocurrency symbols mentioned, uppercase\n"
    "- relevance: high=tradable signal, low/noise=ignore\n"
    "- is_breaking: time-sensitive news (Fed decision, exchange listing, exploit)\n"
    "- summary: 1 sentence, English\n\n"
    "Return ONLY the JSON, no extra text."
)


class GroqError(Exception):
    """Groq API call failed."""


@dataclass(frozen=True)
class TweetClassification:
    """Результат классификации одного твита.

    Fields:
    - sentiment: -1..+1
    - tokens: tuple of cashtags / mentions (uppercase)
    - relevance: 'high' / 'medium' / 'low' / 'noise'
    - is_breaking: time-sensitive (breaking news)
    - summary: 1-sentence summary
    """

    sentiment: float
    tokens: tuple[str, ...]
    relevance: str
    is_breaking: bool
    summary: str


class GroqClient:
    """httpx-wrapper над Groq Chat Completions API (OpenAI-compatible)."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _DEFAULT_MODEL,
        api_url: str = _GROQ_API_URL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("GroqClient requires non-empty api_key")
        self._api_key = api_key
        self._model = model
        self._api_url = api_url
        self._client = client
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=_TIMEOUT_S)
        return self._client

    async def classify_tweet(self, tweet_text: str) -> TweetClassification:
        """Классификация одного твита.

        Bombs out с GroqError если API недоступен / response невалиден.
        Caller (aggregator) сам решает retry / fallback стратегию.
        """
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": tweet_text},
            ],
            "temperature": 0.0,  # детерминированно — classification task
            "max_tokens": 256,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        client = self._get_client()
        try:
            resp = await client.post(self._api_url, headers=headers, json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise GroqError(f"Groq HTTP {e.response.status_code}: {e.response.text[:200]}") from e
        except Exception as e:
            raise GroqError(f"Groq request failed: {e}") from e

        data = resp.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise GroqError(f"Groq response malformed: {data!r}") from e

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise GroqError(f"Groq returned non-JSON content: {content[:200]}") from e

        return _parse_classification(parsed)


def _parse_classification(payload: dict[str, Any]) -> TweetClassification:
    """Парсит и валидирует output Groq.

    Bombs out с GroqError если поля невалидны.
    """
    try:
        sentiment_raw = payload["sentiment"]
        tokens_raw = payload["tokens"]
        relevance = payload["relevance"]
        is_breaking = payload["is_breaking"]
        summary = payload["summary"]
    except KeyError as e:
        raise GroqError(f"Groq output missing field: {e}") from e

    if not isinstance(sentiment_raw, int | float):
        raise GroqError(f"sentiment must be number, got {type(sentiment_raw).__name__}")
    sentiment = float(sentiment_raw)
    if not -1.0 <= sentiment <= 1.0:
        raise GroqError(f"sentiment={sentiment} out of [-1, 1]")

    if not isinstance(tokens_raw, list):
        raise GroqError(f"tokens must be list, got {type(tokens_raw).__name__}")
    if not all(isinstance(t, str) for t in tokens_raw):
        raise GroqError("tokens must contain only strings")

    if relevance not in {"high", "medium", "low", "noise"}:
        raise GroqError(f"relevance='{relevance}' not in allowed set")

    if not isinstance(is_breaking, bool):
        raise GroqError(f"is_breaking must be bool, got {type(is_breaking).__name__}")

    if not isinstance(summary, str) or not summary.strip():
        raise GroqError("summary must be non-empty string")

    return TweetClassification(
        sentiment=sentiment,
        tokens=tuple(tokens_raw),
        relevance=relevance,
        is_breaking=is_breaking,
        summary=summary.strip(),
    )
