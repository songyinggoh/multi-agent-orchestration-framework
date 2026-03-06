"""ScriptedLLM: deterministic mock LLM for testing.

Returns pre-defined responses in order. Enables fully deterministic,
fast unit tests for agent workflows without API calls.

Usage:
    from orchestra.testing import ScriptedLLM

    llm = ScriptedLLM([
        "I'll search for that.",
        "Here are the results.",
        LLMResponse(content="Final answer.", tool_calls=[...]),
    ])

    response = await llm.complete(messages)  # "I'll search for that."
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from orchestra.core.types import LLMResponse, Message, ModelCost, StreamChunk


class ScriptExhaustedError(Exception):
    """Raised when ScriptedLLM has no more scripted responses."""


class ScriptedLLM:
    """Deterministic mock LLM that returns pre-scripted responses.

    Implements the LLMProvider protocol for testing.
    """

    def __init__(self, responses: list[LLMResponse | str]) -> None:
        self._responses: list[LLMResponse] = []
        for r in responses:
            if isinstance(r, str):
                self._responses.append(LLMResponse(content=r))
            else:
                self._responses.append(r)
        self._index = 0
        self._call_log: list[dict[str, Any]] = []

    @property
    def provider_name(self) -> str:
        return "scripted"

    @property
    def default_model(self) -> str:
        return "scripted-test"

    async def complete(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        output_type: type[BaseModel] | None = None,
    ) -> LLMResponse:
        """Return the next scripted response."""
        self._call_log.append({
            "messages": messages,
            "model": model,
            "tools": tools,
            "temperature": temperature,
        })

        if self._index >= len(self._responses):
            raise ScriptExhaustedError(
                f"ScriptedLLM exhausted after {len(self._responses)} calls.\n"
                f"  Fix: Add more responses to the script."
            )

        response = self._responses[self._index]
        self._index += 1
        return response

    async def stream(
        self,
        messages: list[Message],
        *,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream the next scripted response word by word."""
        response = await self.complete(
            messages, model=model, tools=tools,
            temperature=temperature, max_tokens=max_tokens,
        )

        if response.content:
            words = response.content.split()
            for word in words:
                yield StreamChunk(content=word + " ", model=model or "scripted")

    def count_tokens(self, messages: list[Message], model: str | None = None) -> int:
        return sum(len(m.content) // 4 for m in messages)

    def get_model_cost(self, model: str | None = None) -> ModelCost:
        return ModelCost()

    @property
    def call_count(self) -> int:
        return len(self._call_log)

    @property
    def call_log(self) -> list[dict[str, Any]]:
        return self._call_log

    def reset(self) -> None:
        self._index = 0
        self._call_log.clear()
