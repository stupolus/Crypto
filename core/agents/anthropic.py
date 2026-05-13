"""AnthropicAgent — реальный subagent поверх Anthropic Messages API.

Использование (на примере подкласса):

    class MarketAnalystAgent(AnthropicAgent):
        name = "market_analyst"
        model = "claude-sonnet-4-6"
        system_prompt = "Ты quant-аналитик..."
        user_prompt_template = "Symbol: {symbol}, candles: {candles_json}"
        required_response_keys = ("state", "volatility")

        def _validate_payload(self, payload: dict) -> None:
            super()._validate_payload(payload)  # required_keys check
            assert payload["state"] in {"TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND"}

Конструктор берёт ``api_key`` + опциональный ``httpx.AsyncClient`` (для тестов
через respx). См. plans/17 §3 для рекомендаций по моделям и промптам.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, ClassVar

import httpx

from core.agents.base import AgentExecutionError, AgentRequest, AgentResponse, BaseAgent

logger = logging.getLogger(__name__)

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_API_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 2048


class AnthropicAgent(BaseAgent):
    """Базовый класс для subagent'ов на Anthropic Messages API.

    Подклассы определяют:
    - ``name`` / ``model`` (из BaseAgent)
    - ``system_prompt`` — статический system promprt
    - ``user_prompt_template`` — Python-string с {placeholders}, format(**req.context)
    - ``required_response_keys`` — список ключей которые ОБЯЗАТЕЛЬНО в payload

    JSON-парсинг: ищем первый {...} в ответе модели. Anthropic иногда
    оборачивает в ```json ... ``` блок — обрабатываем оба случая.

    Cost tracking: AgentResponse.tokens_in/out из API response.
    """

    user_prompt_template: ClassVar[str] = "{prompt}"
    required_response_keys: ClassVar[tuple[str, ...]] = ()
    max_tokens: ClassVar[int] = _DEFAULT_MAX_TOKENS

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
        api_url: str = _ANTHROPIC_API_URL,
    ) -> None:
        if not api_key:
            raise ValueError("AnthropicAgent requires non-empty api_key")
        self._api_key = api_key
        self._api_url = api_url
        self._client = client
        self._owns_client = client is None

    async def aclose(self) -> None:
        """Закрывает внутренний httpx-клиент (если был создан агентом)."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _format_user_prompt(self, context: dict[str, Any]) -> str:
        try:
            return self.user_prompt_template.format(**context)
        except KeyError as e:
            raise AgentExecutionError(
                f"{self.name}: missing context key {e} for user_prompt_template"
            ) from e

    async def _execute(self, req: AgentRequest) -> AgentResponse:
        user_prompt = self._format_user_prompt(req.context)
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": self.system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        client = self._get_client()
        try:
            resp = await client.post(
                self._api_url, headers=headers, json=body, timeout=req.timeout_s
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise AgentExecutionError(
                f"{self.name}: Anthropic HTTP {e.response.status_code}: {e.response.text[:300]}"
            ) from e
        except Exception as e:
            raise AgentExecutionError(f"{self.name}: HTTP call failed: {e}") from e

        data = resp.json()
        try:
            raw_text = data["content"][0]["text"]
            usage = data.get("usage", {})
            tokens_in = int(usage.get("input_tokens", 0))
            tokens_out = int(usage.get("output_tokens", 0))
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise AgentExecutionError(
                f"{self.name}: malformed Anthropic response: {e}; body={data!r}"
            ) from e

        payload = _extract_json_payload(raw_text)
        return AgentResponse(
            payload=payload,
            raw_text=raw_text,
            model=self.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        missing = [k for k in self.required_response_keys if k not in payload]
        if missing:
            raise AgentExecutionError(f"{self.name}: payload missing required keys: {missing}")


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```", re.DOTALL)
_JSON_INLINE_RE = re.compile(r"(\{.*\})", re.DOTALL)


def _extract_json_payload(text: str) -> dict[str, Any]:
    """Достать JSON-объект из ответа модели.

    Сценарии:
    1. Полный ответ — это JSON: ``{...}``
    2. Обёрнут в ```json блок: ``` json\n{...}\n``` ``
    3. JSON где-то внутри natural-language ответа

    Бросает AgentExecutionError если ничего распарсить не удалось.
    """
    text = text.strip()
    # Сценарий 2: code block
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            result: Any = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(result, dict):
                return result

    # Сценарий 1 / 3: первый {...}
    m = _JSON_INLINE_RE.search(text)
    if m:
        try:
            result = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(result, dict):
                return result

    raise AgentExecutionError(f"Could not extract JSON payload from response: {text[:200]}")
