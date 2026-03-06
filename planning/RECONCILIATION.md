# Orchestra: Design Reconciliation Document

**Date:** 2026-03-07
**Status:** AUTHORITATIVE — This document resolves all cross-document conflicts.
**Rule:** Where any other document contradicts this one, THIS document wins.

---

## Purpose

Three audits identified 18 cross-document inconsistencies, 17 Phase 1 plan gaps, 6 unanswered integration questions, and 5 practical blind spots. This document makes a binding decision on every conflict point. The Phase 1 plan (PHASE1-PLAN.md) must be updated to match these decisions before implementation begins.

---

## 1. IDENTITY & LEGAL

### 1.1 Package Name

**Decision: `orchestra-agents`**

| Name | PyPI Status |
|---|---|
| `orchestra` | TAKEN (v1.0.60, actively maintained) |
| `orchestra-ai` | TAKEN (v0.0.1 placeholder) |
| `pyorchestra` | TAKEN (v0.6.2, active) |
| `orchestra-sdk` | TAKEN (v0.1.2) |
| `orchestrai` | AVAILABLE |
| `orchestra-agents` | AVAILABLE |
| `orchestraflow` | AVAILABLE |

Rationale: `orchestra-agents` is descriptive, SEO-friendly ("orchestra agents python" will find it), and the Python import name remains `orchestra` (via `[tool.hatch.build.targets.wheel] packages = ["src/orchestra"]`). Users still write `from orchestra import agent`. The PyPI distribution name and the import name are decoupled.

- **PyPI name:** `orchestra-agents`
- **Import name:** `orchestra`
- **CLI command:** `orchestra`
- **GitHub org:** `orchestra-agents` (verify availability)
- **Docs domain:** TBD

### 1.2 License

**Decision: Apache 2.0**

Source: `STRATEGIC-POSITIONING.md` and `SUMMARY.md` both specify Apache 2.0. The MIT in PHASE1-PLAN.md was a transcription error.

Changes needed:
- `pyproject.toml`: `license = "Apache-2.0"`
- Classifiers: `"License :: OSI Approved :: Apache Software License"`
- `LICENSE` file: Apache 2.0 full text

---

## 2. CORE TYPES & PROTOCOLS

### 2.1 Agent Protocol — `run()` Signature

**Decision: Use architecture-plan.md style with ExecutionContext**

```python
async def run(self, input: str | list[Message], context: ExecutionContext) -> AgentResult
```

Rationale: `ExecutionContext` is required for state access, secrets, observability, and memory. A plain `dict` is insufficient. `input` accepts both `str` (simple case) and `list[Message]` (full conversation).

### 2.2 Agent Property — `instructions` vs `system_prompt`

**Decision: `system_prompt`**

Rationale: More explicit than `instructions`. Matches what it actually is — the system message sent to the LLM. Both PHASE1-PLAN and API-DESIGN use `system_prompt`. The architecture-plan's `instructions` (from Swarm naming) is overridden.

Dynamic prompts supported via `build_system_prompt(context: ExecutionContext) -> str` method override on class-based agents. For decorator agents, `{variable}` template syntax in docstrings is resolved from function arguments.

### 2.3 `END` Sentinel

**Decision: Sentinel object (not string)**

```python
class _EndSentinel:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def __repr__(self) -> str: return "END"
    def __eq__(self, other) -> bool: return isinstance(other, _EndSentinel)
    def __hash__(self) -> int: return hash("__orchestra_end__")

END = _EndSentinel()
```

Rationale: Sentinel object avoids accidental collision with user strings. Singleton pattern ensures `END is END` works. `START` constant (`"__start__"` string) is kept for entry point naming only — it's an internal convention, not a user-facing sentinel.

### 2.4 `AgentResult` Shape

**Decision: Merged superset from architecture-plan + PHASE1-PLAN**

```python
class AgentResult(BaseModel):
    agent_name: str
    output: str                                          # LLM text output (always str)
    structured_output: BaseModel | None = None           # Parsed output_type if defined
    messages: list[Message] = Field(default_factory=list) # Full conversation
    tool_calls_made: list[ToolCallRecord] = Field(default_factory=list)
    handoff_to: str | None = None                        # Handoff target (Phase 2)
    state_updates: dict[str, Any] = Field(default_factory=dict)  # Explicit state writes
    token_usage: TokenUsage | None = None
```

Key change: `context_updates` renamed to `state_updates` for clarity.

### 2.5 `TokenUsage` Field Names

**Decision: Provider-neutral naming (architecture-plan style)**

```python
class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
```

Rationale: `input_tokens`/`output_tokens` is provider-neutral. OpenAI's `prompt_tokens`/`completion_tokens` is mapped during provider adapter conversion. Anthropic already uses `input_tokens`/`output_tokens`.

### 2.6 Reducer Names

**Decision: API-DESIGN.md names**

| Authoritative Name | PHASE1-PLAN Name (deprecated) |
|---|---|
| `merge_list` | `append_reducer` |
| `merge_dict` | `merge_dict_reducer` |
| `sum_numbers` | `add_reducer` |
| `last_write_wins` | `last_write_wins` (same) |
| `merge_set` | (new) |
| `concat_str` | (new) |
| `keep_first` | (new) |
| `max_value` | (new) |
| `min_value` | (new) |

Phase 1 ships all 9 reducers.

---

## 3. GRAPH ENGINE

### 3.1 `WorkflowGraph` Constructor

**Decision: Optional state schema (inferred when possible)**

```python
class WorkflowGraph:
    def __init__(self, state_schema: type[BaseModel] | None = None, name: str = ""):
```

- If `state_schema` is provided, use it.
- If omitted with fluent API (`.then()`), infer a default state with `messages: list[Message]` and `output: str`.
- If omitted with explicit API (`add_node`), require `state_schema` at `compile()` time if parallel nodes exist.

Parameter name: `state_schema` (not `state_class`).

### 3.2 Fluent Builder API — Phase Assignment

**Decision: Phase 1 includes the fluent API**

The fluent builder (`.then()`, `.parallel()`, `.branch()`, `.if_then()`, `.loop()`) is essential to the DX differentiation claim. Without it, Orchestra's Quick Start is as verbose as LangGraph, invalidating the core value proposition.

Phase 1 fluent methods: `.then()`, `.parallel()`, `.join()`, `.branch()`, `.if_then()`, `.loop()`
Phase 2 fluent methods: `.handoff()`, `.dynamic()`, `.subgraph()`, `.route_on_output()`

The fluent methods are syntactic sugar over `add_node()`/`add_edge()`. They auto-generate node IDs from agent names (e.g., `researcher` from `@agent` name or class name). Fluent and explicit APIs can be mixed: `.then()` returns `self` and populates the same internal node/edge structures.

### 3.3 `max_turns` Default

**Decision: 50**

All documents except one API-DESIGN comment agree on 50. The comment saying 100 is a typo.

### 3.4 `add_handoff()` and `add_loop()` Phase Assignment

- `add_loop()` + `.loop()`: **Phase 1** (it's a conditional back-edge — simple to implement)
- `add_handoff()` + `.handoff()`: **Phase 2** (requires context transfer design)

---

## 4. LLM PROVIDER

### 4.1 Default Provider Strategy

**Decision: Generic OpenAI-compatible HTTP provider as the built-in default**

The core package ships with a generic `HttpProvider` that speaks the OpenAI chat completions API format over raw `httpx`. No extra dependencies beyond what's already in core. This works out of the box with:

- **OpenAI** (api.openai.com)
- **Ollama** (localhost:11434)
- **vLLM** (any OpenAI-compatible endpoint)
- **LiteLLM proxy**
- **Azure OpenAI**
- **Any OpenAI-compatible API**

`pip install orchestra-agents` just works. No extras needed for basic usage.

Optional extras (`openai`, `anthropic`, `google-generativeai`) provide native SDK adapters with richer features (native streaming, token counting, structured output modes) but are not required.

### 4.2 Method Names

**Decision: API-DESIGN.md names**

```python
class LLMProvider(Protocol):
    @property
    def provider_name(self) -> str: ...
    @property
    def default_model(self) -> str: ...
    async def complete(self, messages: list[Message], *, model: str | None = None,
                       tools: list[ToolSchema] | None = None,
                       temperature: float = 0.7, max_tokens: int | None = None,
                       output_type: type[BaseModel] | None = None) -> LLMResponse: ...
    async def stream(self, messages: list[Message], **kwargs) -> AsyncIterator[StreamChunk]: ...
    def count_tokens(self, messages: list[Message], model: str | None = None) -> int: ...
    def get_model_cost(self, model: str | None = None) -> ModelCost: ...
```

Method names: `complete()` (not `chat()`), `stream()` (not `stream_chat()`/`chat_stream()`).
No `embed()` in Phase 1 — deferred to Phase 3 (memory system).

### 4.3 Built-in HttpProvider (Phase 1)

```python
class HttpProvider:
    """
    Generic OpenAI-compatible HTTP provider. Zero extra dependencies.
    Works with any endpoint that speaks the OpenAI chat completions format.
    """
    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",  # default
        api_key: str | None = None,                     # from env if not provided
        default_model: str = "gpt-4o-mini",
    ): ...

# Usage — works with any OpenAI-compatible API:
from orchestra.providers import HttpProvider

# OpenAI (default)
provider = HttpProvider(api_key="sk-...")

# Ollama (local)
provider = HttpProvider(base_url="http://localhost:11434/v1", default_model="llama3")

# vLLM / LiteLLM / Azure / etc.
provider = HttpProvider(base_url="https://my-endpoint/v1", api_key="...")
```

Optional native SDK adapters (`AnthropicProvider`, `GoogleProvider`) are available as extras for providers that don't speak the OpenAI format. Anthropic's API differs enough to warrant a dedicated adapter.

### 4.4 Provider Resolution from Model String

**Decision: Prefix-based inference with explicit override**

```python
# Automatic inference (default)
PROVIDER_PREFIXES = {
    "gpt-": "openai_compat", "o1-": "openai_compat", "o3-": "openai_compat",
    "claude-": "anthropic",   # requires orchestra-agents[anthropic]
    "gemini-": "google",      # requires orchestra-agents[google]
    "llama-": "ollama", "mistral-": "ollama", "qwen-": "ollama",
}

# Explicit override always wins
@agent(model="gpt-4o", provider="azure_openai")
```

For `openai_compat` and `ollama` prefixes, the built-in `HttpProvider` is used — no extras needed. For `claude-` and `gemini-`, the framework checks if the native SDK is installed and falls back to a clear error: `"Anthropic provider requires: pip install orchestra-agents[anthropic]"`.

A `ProviderRegistry` resolves model strings to provider instances. `CompiledGraph` receives a `ProviderRegistry` at `compile()` or uses the global default. Providers are registered at startup via `configure_providers()` or auto-detected from environment variables (`OPENAI_API_KEY` present → HttpProvider with OpenAI base_url; `OLLAMA_HOST` present → HttpProvider with Ollama base_url).

### 4.5 Provider Injection into Agents

**Decision: Executor injects provider via ExecutionContext**

```python
# In AsyncioExecutor._execute_agent_node():
provider = self.provider_registry.resolve(agent.model, agent.provider)
context = ExecutionContext(state=state, provider=provider, ...)
result = await agent.run(input, context)
```

Agents never hold a direct provider reference. They receive it via `context.provider` at execution time. This enables testing (ScriptedLLM injected via context) and cost routing (CostRouter swaps provider transparently).

---

## 5. AGENT OUTPUT → STATE MERGE (Critical Integration Seam)

**Decision: Three-layer merge strategy**

This is the most important design decision. When an AgentNode completes, the executor merges its output into workflow state as follows:

```
Layer 1: state_updates dict (explicit)
  — Agent returns AgentResult(state_updates={"status": "done", "confidence": 0.9})
  — Each key is merged via its field's reducer (or last_write_wins if no reducer)

Layer 2: output → designated state field (automatic)
  — AgentResult.output (str) is written to state field named by the node's `output_key`
  — Default output_key: "{node_id}_output" (e.g., "researcher_output")
  — Configurable: graph.add_node("research", agent, output_key="research_findings")

Layer 3: structured_output field mapping (automatic, opt-in)
  — If agent has output_type and state has matching field names, merge field-by-field
  — Only if node is configured with `map_output=True`
  — e.g., ResearchReport(summary=..., sources=[...]) maps to state.summary and state.sources
```

For the fluent API `.then()` chain without explicit state:
- A default state schema is inferred with `messages: list[Message]` and `output: str`
- Each agent's output overwrites `state.output` (last_write_wins)
- Each agent's messages are appended to `state.messages` (merge_list)
- This covers the 80% simple case

For parallel fan-in:
- Each parallel agent's `state_updates` are merged via reducers
- Each parallel agent's `output` is written to its own `output_key`
- Without a state class, parallel writes to the same key raise `StateConflictError` (never silently drop data)

---

## 6. EXECUTION CONTEXT

**Decision: Phase 1 includes ExecutionContext with a narrow interface**

```python
@dataclass
class ExecutionContext:
    # Core (Phase 1)
    run_id: str
    thread_id: str
    turn_number: int
    node_id: str
    state: BaseModel | dict          # Current workflow state (read-only view)
    provider: LLMProvider            # Injected LLM provider
    tool_registry: ToolRegistry      # Available tools

    # Convenience methods (Phase 1)
    async def update_state(self, updates: dict[str, Any]) -> None: ...
    def get_config(self, key: str, default: Any = None) -> Any: ...

    # Extended (Phase 2+)
    # memory: MemoryManager         # Phase 3
    # identity: AgentIdentity       # Phase 4
    # telemetry: TelemetryEmitter   # Phase 2
    # secrets: SecretProvider        # Phase 4
```

To prevent God-object growth, subsystems are added as optional attributes in later phases. Phase 1 keeps it minimal: run metadata, state, provider, tools.

---

## 7. ERROR HIERARCHY

**Decision: Single file `src/orchestra/core/errors.py` with domain-based hierarchy**

```
OrchestraError (base)
├── GraphError
│   ├── GraphCompileError
│   ├── UnreachableNodeError
│   ├── CycleWithoutGuardError
│   └── StateConflictError
├── AgentError
│   ├── AgentTimeoutError
│   ├── OutputValidationError
│   └── MaxIterationsError
├── ProviderError
│   ├── RateLimitError (retry_after_seconds)
│   ├── AuthenticationError
│   ├── ContextWindowError (context_length, max_context_length)
│   └── ProviderUnavailableError
├── ToolError
│   ├── ToolNotFoundError
│   ├── ToolTimeoutError
│   ├── ToolPermissionError
│   └── ToolExecutionError
└── StateError
    ├── ReducerError
    └── StateValidationError
```

Phase 1 ships the above. The enhanced anomaly taxonomy from `architecture-refinements.md` (IntraAgentError, InterAgentError, etc.) is deferred to Phase 2+ and added as subclasses under the existing hierarchy.

---

## 8. TOP-LEVEL API (`run()`, `RunResult`)

**Decision: Phase 1 includes `run()`, `run_sync()`, and `RunResult`**

```python
# src/orchestra/__init__.py re-exports:
from orchestra.core.agent import Agent, BaseAgent, agent
from orchestra.core.graph import WorkflowGraph
from orchestra.core.state import WorkflowState
from orchestra.core.types import Message, END
from orchestra.core.errors import OrchestraError
from orchestra.core.runner import run, run_sync, RunResult
from orchestra.tools.base import tool

class RunResult(BaseModel):
    output: str | BaseModel
    state: dict[str, Any]
    messages: list[Message]
    run_id: str
    duration_ms: float
    total_tokens: int
    total_cost_usd: float
    node_execution_order: list[str]
```

`run()` is async. `run_sync()` wraps it with `asyncio.run()` for scripts and notebooks.

---

## 9. TESTING PACKAGE

**Decision: `src/orchestra/testing/` is a public package in Phase 1**

```
src/orchestra/testing/
    __init__.py          # re-exports ScriptedLLM
    scripted.py          # ScriptedLLM (Phase 1)
    simulated.py         # SimulatedLLM (Phase 3)
    flaky.py             # FlakyLLM (Phase 3)
    assertions.py        # Workflow assertions (Phase 3)
```

Users install Orchestra and immediately get `from orchestra.testing import ScriptedLLM`.

---

## 10. MEMORY → LLM CONTEXT INJECTION

**Decision: Deferred to Phase 3, but the contract is defined now**

Memory injection happens in the executor, not in the agent. When `MemoryConfig` is enabled on an agent:

1. Before LLM call: executor queries `MemoryManager.retrieve(query=last_user_message, agent=agent_name, limit=10)`
2. Retrieved memories are prepended to the system prompt as a `[MEMORY]` block
3. Token budget for memories: 20% of model's context window (configurable)
4. If memories + conversation exceed context window: memories are truncated first, then oldest conversation messages

Phase 1 agents have `memory_enabled: bool = False` (no-op). Phase 3 activates the injection pipeline.

---

## 11. EVENT SOURCING ↔ REDUCER COORDINATION

**Decision: Executor coordinates both in a single step**

```python
# In AsyncioExecutor, after a node completes:
async def _apply_node_result(self, node_id, result, state, event_store):
    # 1. Write event (source of truth)
    event = AgentEvent(type=EventType.STATE_UPDATED, node_id=node_id, data=result.state_updates)
    await event_store.append(event)

    # 2. Apply reducer (current state projection)
    new_state = self.state_reducer.apply(state, result.state_updates)

    # 3. Checkpoint (for time-travel)
    await event_store.create_snapshot(state=new_state)

    return new_state
```

During replay: events are read in order, each event's `data` is fed through reducers sequentially, producing the reconstructed state.

Phase 1 implements the reducer step only (no event store). Phase 2 adds event sourcing on top with the same reducer logic.

---

## 12. PRACTICAL GAPS

### 12.1 Cross-Platform CI

**Decision: Add Windows + macOS + Linux to CI matrix in Phase 1**

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
    python-version: ["3.11", "3.12", "3.13"]
```

### 12.2 Core vs Optional Dependencies

**Decision: Minimal core, everything else optional**

Core (always installed): `pydantic`, `httpx`, `structlog`, `rich`, `typer`, `anyio`
Phase 1 optional: `anthropic` (for Claude models), `google-generativeai` (for Gemini)
Not needed as extras: `openai` — the built-in `HttpProvider` covers all OpenAI-compatible APIs via raw `httpx`
Phase 2+ optional: `aiosqlite`, `fastapi`, `uvicorn`, `sse-starlette`, `opentelemetry-sdk`, `asyncpg`, `redis`, `ray`, `nats-py`

The `~15 core packages` claim in SUMMARY.md is corrected to `6 core + optional extras`.

### 12.3 Graph Visualization

**Decision: Phase 1 includes `compiled.to_mermaid() -> str`**

Low effort, high impact. Outputs Mermaid diagram syntax that renders in GitHub, VS Code, and documentation. No external dependencies needed.

### 12.4 Error Message Quality Standard

**Decision: Every error includes (a) what happened, (b) where, (c) how to fix**

Example:
```
GraphCompileError: Unreachable node "editor" — no incoming edges.
  Defined at: graph.add_node("editor", editor_agent)
  Fix: Add an edge to "editor", e.g.: graph.add_edge("writer", "editor")
```

### 12.5 Contribution Infrastructure

**Decision: Phase 1 includes CONTRIBUTING.md, CODE_OF_CONDUCT.md, LICENSE**

Minimum viable open-source hygiene. Created during project scaffolding task.

---

## 13. GUARDRAILS PHASE ASSIGNMENT

**Decision: Phase 3 (per ROADMAP)**

The `architecture-refinements.md` assignment to Phase 2 is overridden. Guardrails are a Phase 3 feature as specified in the ROADMAP. The ROADMAP is authoritative for phase assignments.

---

## 14. ORCHESTRATION PATTERN CONSTRUCTORS

**Decision: Phase 2 (not Phase 1)**

`react_loop()`, `plan_and_execute()`, `deterministic_pipeline()` etc. from `architecture-refinements.md` are deferred to Phase 2. Phase 1 focuses on the raw graph primitives. Pattern constructors are syntactic sugar over those primitives.

---

## 15. PHASE 1 PLAN — REQUIRED ADDITIONS

The following must be added to PHASE1-PLAN.md before implementation:

| # | Addition | Effort |
|---|---|---|
| 1 | `src/orchestra/core/context.py` — ExecutionContext | Small |
| 2 | `src/orchestra/core/errors.py` — Centralized error hierarchy | Small |
| 3 | `src/orchestra/core/runner.py` — `run()`, `run_sync()`, `RunResult` | Medium |
| 4 | Fluent builder methods on WorkflowGraph | Medium |
| 5 | Provider resolution + injection via ExecutionContext | Medium |
| 6 | `src/orchestra/testing/__init__.py` + `scripted.py` (move from fixtures) | Small |
| 7 | `__init__.py` re-exports | Small |
| 8 | `compiled.to_mermaid()` | Small |
| 9 | All 9 reducer functions with standard names | Small |
| 10 | Structured output enforcement in agent run loop | Small |
| 11 | CONTRIBUTING.md, CODE_OF_CONDUCT.md, LICENSE | Small |
| 12 | Cross-platform CI matrix | Small |

### PHASE 1 PLAN — REQUIRED CORRECTIONS

| # | Correction |
|---|---|
| 1 | License: MIT → Apache 2.0 |
| 2 | Package name: `orchestra` → `orchestra-agents` |
| 3 | Agent Protocol: `context: dict` → `context: ExecutionContext` |
| 4 | AgentResult: Add `structured_output`, `state_updates`, `token_usage` |
| 5 | END: String `"__end__"` → Sentinel object |
| 6 | TokenUsage: `prompt_tokens` → `input_tokens`, `completion_tokens` → `output_tokens` |
| 7 | Reducer names: `append_reducer` → `merge_list`, etc. |
| 8 | WorkflowGraph: `state_class` → `state_schema`, make optional |
| 9 | LLMProvider methods: `chat()` → `complete()`, `chat_stream()` → `stream()` |
| 10 | Agent property: Confirm `system_prompt` (already correct in PHASE1-PLAN) |

---

## Document Hierarchy (Authority Order)

1. **RECONCILIATION.md** (this document) — Resolves all conflicts
2. **PHASE1-PLAN.md** (after updates) — Executable implementation spec for Phase 1
3. **API-DESIGN.md** — Public API reference (authoritative for user-facing API shape)
4. **ROADMAP.md** — Phase assignments and success criteria
5. **architecture-plan.md** — Module structure reference
6. **architecture-refinements.md** — Enhancement proposals (not authoritative until assigned to a phase)
7. **research/*.md** — Historical research (informational only)
