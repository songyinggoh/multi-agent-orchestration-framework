# API Designer Agent Memory

## Project: Orchestra Multi-Agent Framework

**Project root:** `C:\Users\user\Desktop\multi-agent orchestration framework\`
**Key docs:**
- `research/SUMMARY.md` — full research synthesis with architecture decisions
- `research/tech-stack-recommendation.md` — stack rationale (Python 3.11+, asyncio, Pydantic v2, FastAPI, SQLite/PG, NATS, OTel)
- `planning/API-DESIGN.md` — completed public API design (v1.0, 2026-03-05)

## Core Design Decisions (Confirmed)

### Agent Definition
- Three styles (class / decorator / YAML) all compile to internal `AgentSpec`
- Class style uses `ClassVar` annotations (not Pydantic fields) for class-level config
- Decorator style: function body is intentionally empty — docstring becomes system prompt
- YAML is style 3 (least powerful), not style 1

### State Model
- Pydantic `BaseModel` extending `WorkflowState` (not TypedDict)
- Reducers via `Annotated[list[str], merge_list]` pattern
- Parallel fan-in reducer ordering: alphabetical by agent name (reproducible)
- `StateConflictError` at compile time when parallel agents write to same field without reducer

### Graph API
- Fluent builder: `.then()`, `.parallel()`, `.join()`, `.branch()`, `.if_then()`, `.handoff()`, `.loop()`, `.subgraph()`, `.dynamic()`
- `compile()` is the validation gate — structural errors must surface there, not at runtime
- Cycles without `max_iterations` or `max_turns` guard = `GraphCompileError` (required safety)
- `DynamicNode` for plan-and-execute (LangGraph cannot do this — graphs are static after compile)

### Routing Patterns (Three mechanisms)
- `.branch(fn, paths={})` — Python routing function
- `.route_on_output(paths={})` — LLM output determines route
- `.handoff(agent_a, agent_b)` — Swarm-style conversation transfer

### Testing Strategy
- `ScriptedLLM` — deterministic, zero cost, milliseconds (unit tests)
- `FlakyLLM` — chaos testing (timeouts, 500s, truncation)
- `SimulatedLLM` — real cheap model (seed=42, temp=0) for integration tests
- `WorkflowAssertion` — assert on checkpoints, not just final output

### Error Hierarchy Root
- `OrchestraError` → `GraphError`, `AgentError`, `ToolError`, `ProviderError`, `StateError`, `CheckpointError`
- `recoverable: bool` field on every error — drives retry logic

## User Preferences
- No emojis in output
- Absolute file paths in all responses
- Detailed code examples with design rationale and comparison to LangGraph/CrewAI/Swarm
- Period (not colon) before tool calls in prose

## See Also
- `patterns.md` (not yet created) — for detailed pattern notes if needed
