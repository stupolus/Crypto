"""MockAgent — для unit-тестов и dev-режима без API-вызовов.

Возвращает заранее заданный payload без обращения к LLM.
"""

from __future__ import annotations

from typing import Any

from core.agents.base import AgentRequest, AgentResponse, BaseAgent


class MockAgent(BaseAgent):
    """Возвращает фиксированный payload — для тестов / dev.

    Использование:
        agent = MockAgent(
            name="market_analyst",
            mock_payload={"state": "TRENDING_UP", "confidence": 0.8},
        )
        resp = await agent.run(AgentRequest(context={}))
        # resp.payload == {"state": "TRENDING_UP", "confidence": 0.8}
    """

    def __init__(
        self,
        name: str = "mock",
        mock_payload: dict[str, Any] | None = None,
        model: str = "mock",
        required_keys: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self.model = model
        self._payload = mock_payload or {}
        self._required_keys = required_keys

    async def _execute(self, req: AgentRequest) -> AgentResponse:
        return AgentResponse(
            payload=dict(self._payload),
            raw_text=f"<mock response for {self.name}>",
            model=self.model,
            tokens_in=0,
            tokens_out=0,
        )

    def _validate_payload(self, payload: dict[str, Any]) -> None:
        for key in self._required_keys:
            if key not in payload:
                raise ValueError(f"mock payload missing required key: {key}")
