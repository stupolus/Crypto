"""Базовый интерфейс агента — async prompt → JSON response.

Спецификация: plans/17 §3 Subagents.

Каждый агент имеет:
- ``name`` — уникальное имя для логов/трейсинга
- ``model`` — Anthropic модель (opus-4-7 / sonnet-4-6 / haiku-4-5)
- ``system_prompt`` — статический системный промпт
- ``async run(req) -> AgentResponse`` — основной метод

Возможные ошибки:
- ``AgentExecutionError`` — API down, timeout, malformed response
- (тут НЕ хендлится бизнес-логика «agent сказал HOLD» — это валидный response)

Аудит: каждый run логируется в ``OrderJournal.subagent_decisions``
(см. plans/18 Layer 6.1).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class AgentError(Exception):
    """Базовая ошибка слоя агентов."""


class AgentExecutionError(AgentError):
    """API недоступен, timeout, или невалидный JSON в ответе."""


@dataclass(frozen=True)
class AgentRequest:
    """Универсальный вход для агента.

    ``context`` — словарь с данными которые промпт-template подставит.
    Каждый агент сам декларирует обязательные ключи в своём промпте.

    ``timeout_s`` — мягкий timeout. На срабатывании — AgentExecutionError.
    """

    context: dict[str, Any]
    timeout_s: float = 30.0


@dataclass(frozen=True)
class AgentResponse:
    """Универсальный ответ агента.

    ``payload`` — структурированный JSON-выход (валидируется агентом).
    ``raw_text`` — оригинальный ответ модели (для аудита).
    ``model`` — какая модель отвечала (для биллинга и debug).
    ``tokens_in`` / ``tokens_out`` — для cost tracking.
    """

    payload: dict[str, Any]
    raw_text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(ABC):
    """Абстракт базового агента.

    Подклассы:
    1. Реализуют ``async _execute(self, req)`` — основной LLM-call
    2. Реализуют ``_validate_payload(self, payload)`` — проверка output-схемы
    3. Опционально переопределяют ``system_prompt`` и ``model``

    Базовый класс делает:
    - Логирование request/response
    - Catching exceptions → AgentExecutionError
    - Заполнение AgentResponse метаданными
    """

    name: str = "base"
    model: str = "claude-sonnet-4-6"
    system_prompt: str = ""

    @abstractmethod
    async def _execute(self, req: AgentRequest) -> AgentResponse:
        """Конкретный LLM-call. Реализует подкласс."""
        raise NotImplementedError

    @abstractmethod
    def _validate_payload(self, payload: dict[str, Any]) -> None:
        """Проверяет что payload соответствует ожидаемой схеме.

        Raises ``AgentExecutionError`` если схема нарушена.
        """
        raise NotImplementedError

    async def run(self, req: AgentRequest) -> AgentResponse:
        """Главная точка входа.

        Гарантирует:
        - Возврат валидного AgentResponse, или AgentExecutionError
        - Audit-trail через logging
        """
        try:
            response = await self._execute(req)
        except AgentError:
            raise
        except Exception as e:
            raise AgentExecutionError(f"{self.name} execution failed: {e}") from e

        try:
            self._validate_payload(response.payload)
        except AgentError:
            raise
        except Exception as e:
            raise AgentExecutionError(f"{self.name} payload invalid: {e}") from e

        return response
