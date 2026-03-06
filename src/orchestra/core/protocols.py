"""Core protocols (interfaces) for Orchestra framework.

All major components are defined as Protocols (structural subtyping).
Implementations do not need to inherit from these -- they just need
to implement the methods.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from orchestra.core.context import ExecutionContext
from orchestra.core.types import (
    AgentResult,
    LLMResponse,
    Message,
    ModelCost,
    StreamChunk,
    ToolResult,
)


@runtime_checkable
class Agent(Protocol):
    """Protocol for all agent implementations."""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def system_prompt(self) -> str: ...

    @property
    def tools(self) -> list[Tool]: ...

    async def run(
        self,
        input: str | list[Message],
        context: ExecutionContext,
    ) -> AgentResult: ...


@runtime_checkable
class Tool(Protocol):
    """Protocol for tool implementations."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def parameters_schema(self) -> dict[str, Any]: ...

    async def execute(
        self,
        arguments: dict[str, Any],
        *,
        context: ExecutionContext | None = None,
    ) -> ToolResult: ...


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM provider adapters."""

    @property
    def provider_name(self) -> str: ...

    @property
    def default_model(self) -> str: ...

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        output_type: type[BaseModel] | None = None,
    ) -> LLMResponse: ...

    async def stream(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]: ...

    def count_tokens(self, messages: list[Message], model: str | None = None) -> int: ...

    def get_model_cost(self, model: str | None = None) -> ModelCost: ...


@runtime_checkable
class StateReducer(Protocol):
    """Protocol for state field reducers."""

    def __call__(self, existing: Any, new: Any) -> Any: ...
