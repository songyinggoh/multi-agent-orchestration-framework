# Coding Conventions

**Analysis Date:** 2026-03-07

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python modules: `compiled.py`, `base.py`, `registry.py`
- Use `__init__.py` in every package for explicit exports
- Test files use `test_` prefix: `test_core.py`, `test_smoke.py`

**Functions:**
- Use `snake_case` for all functions and methods: `apply_state_update()`, `extract_reducers()`
- Async functions follow the same naming; no `async_` prefix convention
- Private methods use single leading underscore: `_resolve_next()`, `_execute_node()`, `_build_headers()`
- Module-level helpers use single leading underscore: `_get_node_name()`, `_wrap_as_node()`

**Variables:**
- Use `snake_case` for all variables: `state_dict`, `node_id`, `tool_schemas`
- Module-level constants use `UPPER_SNAKE_CASE`: `END`, `START`, `_MODEL_COSTS`
- Private instance attributes use single leading underscore: `self._nodes`, `self._edges`, `self._client`

**Classes:**
- Use `PascalCase`: `WorkflowGraph`, `BaseAgent`, `CompiledGraph`, `ScriptedLLM`
- Protocol classes use bare nouns: `Agent`, `Tool`, `LLMProvider`, `StateReducer`
- Error classes end with `Error`: `OrchestraError`, `GraphCompileError`, `RateLimitError`
- Pydantic models use `PascalCase` nouns: `Message`, `AgentResult`, `LLMResponse`, `TokenUsage`
- Dataclasses use `PascalCase` nouns: `Edge`, `ConditionalEdge`, `AgentNode`, `FunctionNode`

**Type Aliases:**
- Use `PascalCase`: `EdgeCondition`, `NodeFunction`, `GraphNode`, `GraphEdge`
- Defined at module level, directly after imports

**Enums:**
- Inherit from `(str, Enum)` for JSON serialization: `MessageRole`, `NodeStatus`, `WorkflowStatus`
- Members use `UPPER_SNAKE_CASE`: `MessageRole.SYSTEM`, `NodeStatus.RUNNING`

## Code Style

**Formatting:**
- Tool: Ruff formatter (`ruff format`)
- Line length: 100 characters
- Target: Python 3.11+
- Config: `[tool.ruff]` section in `pyproject.toml`

**Linting:**
- Tool: Ruff linter (`ruff check`)
- Enabled rule sets: `E`, `W` (pycodestyle), `F` (pyflakes), `I` (isort), `UP` (pyupgrade), `B` (bugbear), `SIM` (simplify), `RUF` (ruff-specific)
- Ignored rules: `UP042` (str enum compat), `SIM105` (contextlib.suppress)
- Per-file ignores for tests: `RUF012`, `B017`, `S101`
- Config: `[tool.ruff.lint]` in `pyproject.toml`

**Type Checking:**
- Tool: mypy in strict mode
- Config: `[tool.mypy]` in `pyproject.toml`
- Pydantic plugin enabled: `plugins = ["pydantic.mypy"]`
- All public functions require type annotations
- Use `from __future__ import annotations` at top of every module for deferred evaluation

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first line after docstring)
2. Standard library: `asyncio`, `uuid`, `json`, `os`, `time`, `functools`, `inspect`
3. Third-party: `pydantic`, `httpx`, `structlog`, `typer`, `rich`
4. Internal (absolute): `from orchestra.core.types import ...`, `from orchestra.core.errors import ...`

**Style:**
- Use `from X import Y` style for specific names, not `import X`
- Group related imports on one `from` line: `from orchestra.core.types import (END, START, Message, MessageRole)`
- Alphabetize imports within groups (enforced by `ruff` with `I` rule set)

**Path Aliases:**
- No path aliases. All imports use absolute package paths: `from orchestra.core.state import WorkflowState`

## Error Handling

**Hierarchy:**
- All framework errors inherit from `OrchestraError` (defined in `src/orchestra/core/errors.py`)
- Four top-level categories: `GraphError`, `AgentError`, `ProviderError`, `ToolError`, `StateError`
- Each category has specific subclasses (e.g., `RateLimitError(ProviderError)`)

**Error Message Pattern:**
- Always include three parts: (a) what happened, (b) where, (c) how to fix
- Use multi-line f-strings with `\n` separators
- Prefix fix suggestions with `Fix:` label

```python
raise GraphCompileError(
    f"Node '{node_id}' already exists.\n"
    f"  Fix: Use a unique name for each node."
)
```

**Patterns:**
- Re-raise framework errors unchanged; wrap unexpected errors:
```python
try:
    ...
except (AgentError, GraphCompileError):
    raise
except Exception as e:
    raise AgentError(f"Node '{node_id}' failed: {e}") from e
```
- Tool execution errors are caught and returned as `ToolResult` with `error` field, not raised
- Provider HTTP errors are mapped to typed exceptions in `_handle_error_status()` at `src/orchestra/providers/http.py`
- Use `from e` chain for all wrapped exceptions

**Custom Error Attributes:**
- `RateLimitError.retry_after_seconds: float | None`
- `ContextWindowError.context_length: int`, `ContextWindowError.max_context_length: int`

## Logging

**Framework:** structlog (configured in `src/orchestra/observability/logging.py`)

**Setup:**
- Call `setup_logging(level="INFO", json_output=False)` at application startup
- Supports both console (colorized, padded) and JSON output modes

**Usage Pattern:**
```python
import structlog
logger = structlog.get_logger(__name__)
logger.debug("executing_node", node=current_node_id, turn=turns)
```

**Guidelines:**
- Use `structlog.get_logger(__name__)` at module level
- Pass structured key-value pairs, not formatted strings
- Use `debug` level for execution tracing (node execution, state transitions)
- Only `src/orchestra/core/compiled.py` currently uses logging

## Comments

**Module Docstrings:**
- Every `.py` file starts with a triple-quoted module docstring
- Docstrings explain purpose, key concepts, and usage examples
- Format:
```python
"""Module title.

Extended description of the module's purpose.

Usage:
    from orchestra.core.state import WorkflowState
    class MyState(WorkflowState):
        ...
"""
```

**Class and Method Docstrings:**
- All public classes and methods have docstrings
- Use imperative mood: "Execute the agent's reasoning loop."
- Include numbered step descriptions for complex methods
- Private methods may have shorter docstrings

**Inline Comments:**
- Section headers use `# ---- Section Name ----` pattern (see `src/orchestra/core/state.py`)
- Use `# ---` dividers between logical sections (see `src/orchestra/core/errors.py`)
- Inline comments explain "why", not "what"

**JSDoc/TSDoc:**
- Not applicable (Python project)

## Function Design

**Size:**
- Functions typically 10-40 lines
- Largest methods are execution loops (~50 lines in `BaseAgent.run()` and `CompiledGraph.run()`)
- Complex logic is split into private helper methods: `_execute_node()`, `_resolve_next()`, `_execute_parallel()`

**Parameters:**
- Use keyword-only arguments after `*` for optional configuration: `async def complete(self, messages, *, model=None, tools=None, temperature=0.7)`
- Use `dict[str, Any]` for loosely-typed state dicts
- Use concrete Pydantic models for structured data: `Message`, `AgentResult`, `LLMResponse`

**Return Values:**
- Functions return concrete types, not `None` where possible
- State update functions return `dict[str, Any]` (partial state dicts)
- Agent execution returns `AgentResult` Pydantic model
- Graph execution returns `dict[str, Any]` (final state)
- `run()` returns `RunResult` Pydantic model with metrics

**Async Convention:**
- All I/O operations are async: agent execution, LLM calls, tool execution
- `run_sync()` wraps async with `asyncio.run()` for convenience
- Node functions are async: `async def node(state: dict) -> dict`

## Module Design

**Exports:**
- Every `__init__.py` explicitly defines `__all__`
- Re-export key symbols from subpackages in parent `__init__.py`
- Top-level `src/orchestra/__init__.py` re-exports the most-used API surface

**Barrel Files:**
- Each subpackage uses `__init__.py` as a barrel file
- `src/orchestra/core/__init__.py` re-exports all types and errors
- `src/orchestra/tools/__init__.py` re-exports `tool`, `ToolWrapper`, `ToolRegistry`

**Data Models:**
- Use Pydantic `BaseModel` for data transfer objects with validation: `Message`, `AgentResult`, `LLMResponse`
- Use `dataclasses.dataclass(frozen=True)` for simple immutable value objects: `Edge`, `ConditionalEdge`, `AgentNode`
- Use `ExecutionContext` as a mutable `@dataclass` for runtime context injection
- Pydantic `model_config`: set `frozen=True` for immutable models, `arbitrary_types_allowed=True` where needed

**Protocols:**
- Use `typing.Protocol` with `@runtime_checkable` for interfaces (defined in `src/orchestra/core/protocols.py`)
- Four core protocols: `Agent`, `Tool`, `LLMProvider`, `StateReducer`
- Implementations satisfy protocols structurally (no inheritance required)
- Prefer Protocol over ABC (stated in `CONTRIBUTING.md`)

**Sentinel Pattern:**
- `END` sentinel uses singleton pattern via `__new__` override (see `src/orchestra/core/types.py`)
- Implements `__eq__`, `__hash__`, `__repr__` for proper comparison
- `START` is a simple string constant `"__start__"`

---

*Convention analysis: 2026-03-07*
