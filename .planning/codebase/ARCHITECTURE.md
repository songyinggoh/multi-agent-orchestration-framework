# Architecture

**Analysis Date:** 2026-03-07

## Pattern Overview

**Overall:** Graph-based workflow engine with protocol-driven extensibility

**Key Characteristics:**
- Directed graph execution model: workflows are graphs of nodes (agents/functions) connected by edges (sequential, conditional, parallel)
- Protocol-based interfaces: core abstractions (`Agent`, `Tool`, `LLMProvider`, `StateReducer`) defined as Python `Protocol` classes enabling structural subtyping
- Immutable state management: Pydantic-based `WorkflowState` with `Annotated` reducer functions for controlled merge semantics
- Async-first: all execution paths are `async/await`; a `run_sync()` wrapper exists for scripts/notebooks
- Builder pattern: `WorkflowGraph` provides both explicit (`add_node`/`add_edge`) and fluent (`.then`/`.parallel`/`.branch`) APIs, compiling to a `CompiledGraph` for execution

## Layers

**Types Layer:**
- Purpose: Define all data structures (messages, tool calls, agent results, enums, sentinels)
- Location: `src/orchestra/core/types.py`
- Contains: `Message`, `MessageRole`, `ToolCall`, `ToolCallRecord`, `ToolResult`, `TokenUsage`, `AgentResult`, `LLMResponse`, `StreamChunk`, `ModelCost`, `NodeStatus`, `WorkflowStatus`, `END` sentinel, `START` constant
- Depends on: `pydantic`
- Used by: Every other module

**Protocol Layer:**
- Purpose: Define structural interfaces for all pluggable components
- Location: `src/orchestra/core/protocols.py`
- Contains: `Agent`, `Tool`, `LLMProvider`, `StateReducer` protocols (all `@runtime_checkable`)
- Depends on: Types Layer, `ExecutionContext`
- Used by: Agent implementations, Provider implementations, Tool implementations

**State Layer:**
- Purpose: Typed workflow state with reducer-based merge semantics for parallel fan-in
- Location: `src/orchestra/core/state.py`
- Contains: `WorkflowState` base class, 9 built-in reducers (`merge_list`, `merge_dict`, `sum_numbers`, `last_write_wins`, `merge_set`, `concat_str`, `keep_first`, `max_value`, `min_value`), `extract_reducers()`, `apply_state_update()`, `merge_parallel_updates()`
- Depends on: `pydantic`, Errors
- Used by: CompiledGraph execution engine, user-defined state schemas

**Graph Definition Layer:**
- Purpose: Build and validate workflow graph topology before execution
- Location: `src/orchestra/core/graph.py`, `src/orchestra/core/nodes.py`, `src/orchestra/core/edges.py`
- Contains: `WorkflowGraph` builder, `AgentNode`/`FunctionNode`/`SubgraphNode` node types, `Edge`/`ConditionalEdge`/`ParallelEdge` edge types
- Depends on: Types Layer, Errors
- Used by: User code (to define workflows), CompiledGraph (receives validated graph)

**Execution Engine Layer:**
- Purpose: Execute compiled graphs by traversing nodes, applying state updates, and routing via edges
- Location: `src/orchestra/core/compiled.py`
- Contains: `CompiledGraph` with `run()`, `_execute_node()`, `_execute_agent_node()`, `_resolve_next()`, `_execute_parallel()`, `to_mermaid()`
- Depends on: All core layers (nodes, edges, state, context, types)
- Used by: `run()` / `run_sync()` top-level functions

**Agent Layer:**
- Purpose: Define agents that interact with LLM providers through a tool-calling loop
- Location: `src/orchestra/core/agent.py`
- Contains: `BaseAgent` (class-based), `DecoratedAgent` + `@agent` decorator (function-based)
- Depends on: Types, Context, Errors, Protocols (implicitly -- uses provider via `ExecutionContext.provider`)
- Used by: User code, `AgentNode` execution in CompiledGraph

**Tool Layer:**
- Purpose: Define tools that agents can invoke, with auto-generated JSON Schema from type hints
- Location: `src/orchestra/tools/base.py`, `src/orchestra/tools/registry.py`
- Contains: `ToolWrapper` class, `@tool` decorator, `ToolRegistry` for centralized lookup
- Depends on: Types, Context
- Used by: Agent tool-calling loop

**Provider Layer:**
- Purpose: Adapt external LLM APIs to the `LLMProvider` protocol
- Location: `src/orchestra/providers/http.py`
- Contains: `HttpProvider` -- generic OpenAI-compatible HTTP client with retry, error mapping, streaming, cost estimation
- Depends on: Types, Errors, `httpx`
- Used by: User code (injected via `ExecutionContext` or `run()` parameter)

**Observability Layer:**
- Purpose: Structured logging configuration
- Location: `src/orchestra/observability/logging.py`
- Contains: `setup_logging()`, `get_logger()` using `structlog`
- Depends on: `structlog`
- Used by: CompiledGraph execution engine (debug logging)

**Testing Layer:**
- Purpose: Provide deterministic mock LLM for unit testing without API calls
- Location: `src/orchestra/testing/scripted.py`
- Contains: `ScriptedLLM` (implements `LLMProvider` protocol), `ScriptExhaustedError`
- Depends on: Types
- Used by: Test suite

**CLI Layer:**
- Purpose: Command-line interface for project scaffolding and workflow execution
- Location: `src/orchestra/cli/main.py`
- Contains: `version`, `init`, `run` commands via `typer`
- Depends on: Core package (version), `typer`, `rich`
- Used by: End users via `orchestra` command

## Data Flow

**Sequential Workflow Execution:**

1. User builds a `WorkflowGraph` by adding nodes (agents/functions) and edges
2. User calls `graph.compile()` which validates the graph and returns a `CompiledGraph`
3. User calls `compiled.run(initial_state)` or uses `run(graph, input=...)`
4. `CompiledGraph.run()` initializes state (dict or `WorkflowState` from schema), creates `ExecutionContext`
5. Engine enters main loop: execute current node -> apply state update -> resolve next node via edges
6. For `AgentNode`: builds messages from state, calls `agent.run(input, context)`, gets `AgentResult`, applies 3-layer merge strategy (state_updates -> output_key -> structured output mapping)
7. For `FunctionNode`/`SubgraphNode`: calls the function/subgraph with state dict, receives partial state update dict
8. State update applied via `apply_state_update()` using reducers (or last-write-wins)
9. Edge resolution: `Edge` returns fixed target; `ConditionalEdge` calls condition function with state; `ParallelEdge` fans out to concurrent execution then merges
10. Loop continues until reaching `END` sentinel or exceeding `max_turns`
11. Final state dict returned (with `__node_execution_order__` metadata)

**Agent Tool-Calling Loop (inside `BaseAgent.run()`):**

1. Build messages: system prompt + input (string or message list)
2. Call `provider.complete()` with messages and tool schemas
3. If response contains `tool_calls`: execute each tool, append tool results to messages, loop back to step 2
4. If no tool calls: return `AgentResult` with output, messages, tool call records, token usage
5. Enforced by `max_iterations` (default 10) -- raises `MaxIterationsError` if exceeded

**Parallel Fan-Out/Fan-In:**

1. `ParallelEdge` triggers `_execute_parallel()`
2. All target nodes executed concurrently via `asyncio.gather()`
3. If any fail, `AgentError` raised with all error details
4. Successful updates merged sequentially via `merge_parallel_updates()` using reducers
5. Execution continues to `join_node` (or `END`)

**State Management:**
- State is either a plain `dict[str, Any]` (no schema) or a `WorkflowState` subclass (Pydantic model)
- When a schema is provided, `Annotated[type, reducer_fn]` hints define how fields merge
- `apply_state_update()` returns a NEW state instance (immutable update pattern)
- Fields without reducers use last-write-wins semantics
- Unknown fields in updates raise `StateValidationError`

## Key Abstractions

**WorkflowGraph (Builder):**
- Purpose: Construct and validate a workflow graph topology
- Location: `src/orchestra/core/graph.py`
- Pattern: Builder with dual API (explicit + fluent), compiles to immutable `CompiledGraph`
- Fluent methods: `.then()`, `.parallel()`, `.join()`, `.branch()`, `.if_then()`, `.loop()`
- Explicit methods: `.add_node()`, `.add_edge()`, `.add_conditional_edge()`, `.add_parallel()`, `.set_entry_point()`

**CompiledGraph (Execution Engine):**
- Purpose: Execute a validated graph against state
- Location: `src/orchestra/core/compiled.py`
- Pattern: State machine with pre-computed edge lookup map
- Produces Mermaid diagrams via `.to_mermaid()`

**GraphNode (Union Type):**
- Purpose: Polymorphic node that wraps agents, functions, or subgraphs
- Definition: `GraphNode = AgentNode | FunctionNode | SubgraphNode` in `src/orchestra/core/nodes.py`
- `AgentNode` wraps an `Agent` with input/output mappers and a 3-layer merge strategy
- `FunctionNode` wraps a plain `async def(state: dict) -> dict` function
- `SubgraphNode` wraps a nested `CompiledGraph` with optional input/output mappers

**GraphEdge (Union Type):**
- Purpose: Polymorphic edge defining transitions between nodes
- Definition: `GraphEdge = Edge | ConditionalEdge | ParallelEdge` in `src/orchestra/core/edges.py`
- `Edge`: unconditional A -> B
- `ConditionalEdge`: A -> condition(state) -> B|C|D with optional `path_map`
- `ParallelEdge`: A -> [B, C, D] concurrent fan-out with `join_node`

**ExecutionContext:**
- Purpose: Runtime context injected into agents during execution
- Location: `src/orchestra/core/context.py`
- Contains: `run_id`, `thread_id`, `turn_number`, `node_id`, `state` (read-only view), `provider`, `tool_registry`, `config`
- Pattern: Dependency injection -- agents receive context rather than holding references

**Protocols (Structural Interfaces):**
- Purpose: Define contracts for pluggable components without requiring inheritance
- Location: `src/orchestra/core/protocols.py`
- `Agent`: `.name`, `.model`, `.system_prompt`, `.tools`, `.run(input, context) -> AgentResult`
- `Tool`: `.name`, `.description`, `.parameters_schema`, `.execute(args, context) -> ToolResult`
- `LLMProvider`: `.provider_name`, `.default_model`, `.complete()`, `.stream()`, `.count_tokens()`, `.get_model_cost()`
- `StateReducer`: `__call__(existing, new) -> merged`

## Entry Points

**Package Import:**
- Location: `src/orchestra/__init__.py`
- Exports: `WorkflowGraph`, `WorkflowState`, `BaseAgent`, `agent`, `tool`, `run`, `run_sync`, `RunResult`, `ExecutionContext`, `Message`, `MessageRole`, `START`, `END`, `OrchestraError`
- Usage: `from orchestra import WorkflowGraph, agent, run`

**CLI Entry Point:**
- Location: `src/orchestra/cli/main.py` (registered as `orchestra` console script in `pyproject.toml`)
- Commands: `orchestra version`, `orchestra init <name>`, `orchestra run <file>`
- Triggers: Shell command `orchestra`

**Top-Level Run Functions:**
- Location: `src/orchestra/core/runner.py`
- `run(graph, input, provider=...)` -- async entry point, returns `RunResult`
- `run_sync(graph, input, provider=...)` -- sync wrapper via `asyncio.run()`

**CompiledGraph.run():**
- Location: `src/orchestra/core/compiled.py`
- Lower-level execution, returns raw state dict
- Called by `runner.run()` or directly by user code

## Error Handling

**Strategy:** Hierarchical exception classes with diagnostic messages (what happened, where, how to fix)

**Error Hierarchy:**
- `OrchestraError` (base) in `src/orchestra/core/errors.py`
  - `GraphError` -> `GraphCompileError`, `UnreachableNodeError`, `CycleWithoutGuardError`, `StateConflictError`
  - `AgentError` -> `AgentTimeoutError`, `OutputValidationError`, `MaxIterationsError`
  - `ProviderError` -> `RateLimitError` (with `retry_after_seconds`), `AuthenticationError`, `ContextWindowError` (with context lengths), `ProviderUnavailableError`
  - `ToolError` -> `ToolNotFoundError`, `ToolTimeoutError`, `ToolPermissionError`, `ToolExecutionError`
  - `StateError` -> `ReducerError`, `StateValidationError`

**Patterns:**
- Graph validation errors raised at compile time (`graph.compile()`) with actionable fix suggestions
- Provider HTTP errors mapped to specific exception types in `HttpProvider._handle_error_status()`
- Retry with exponential backoff for `RateLimitError` and `ProviderUnavailableError` in `HttpProvider._request_with_retry()`
- Tool execution errors caught and returned as `ToolResult` with `.error` field (non-fatal to agent loop)
- Agent node failures in parallel execution collected and re-raised as `AgentError`
- `max_turns` guard on `CompiledGraph.run()` prevents infinite loops (default 50)
- `max_iterations` guard on `BaseAgent.run()` prevents infinite tool-calling loops (default 10)

## Cross-Cutting Concerns

**Logging:**
- Framework: `structlog` configured in `src/orchestra/observability/logging.py`
- Used by: `CompiledGraph` (debug-level node execution logging via `structlog.get_logger()`)
- Configuration: `setup_logging(level, json_output)` -- supports console and JSON output modes

**Validation:**
- Pydantic v2 used throughout for all data models (`BaseModel`, `model_validate`, `model_dump`)
- State schema validation via `WorkflowState` subclasses
- Unknown state field detection in `apply_state_update()`
- Graph topology validation in `WorkflowGraph._validate()` (entry point exists, edges reference valid nodes)
- Tool parameter schemas auto-generated from Python type hints

**Authentication:**
- LLM provider auth via API key (constructor param or `OPENAI_API_KEY` env var)
- No built-in user authentication layer -- framework-level concern only

**Type Safety:**
- `mypy --strict` configured in `pyproject.toml`
- PEP 561 `py.typed` marker present at `src/orchestra/py.typed`
- All protocols are `@runtime_checkable`
- `from __future__ import annotations` used consistently for forward references

---

*Architecture analysis: 2026-03-07*
