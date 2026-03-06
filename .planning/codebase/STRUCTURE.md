# Codebase Structure

**Analysis Date:** 2026-03-07

## Directory Layout

```
multi-agent orchestration framework/
├── src/
│   └── orchestra/                # Main package (installed as "orchestra-agents")
│       ├── __init__.py           # Public API re-exports
│       ├── py.typed              # PEP 561 type marker
│       ├── core/                 # Core engine: types, state, graph, agents
│       │   ├── __init__.py       # Re-exports core types and errors
│       │   ├── types.py          # All data models (Message, AgentResult, etc.)
│       │   ├── protocols.py      # Protocol interfaces (Agent, Tool, LLMProvider)
│       │   ├── errors.py         # Full error hierarchy
│       │   ├── state.py          # WorkflowState + reducers
│       │   ├── context.py        # ExecutionContext
│       │   ├── graph.py          # WorkflowGraph builder
│       │   ├── nodes.py          # AgentNode, FunctionNode, SubgraphNode
│       │   ├── edges.py          # Edge, ConditionalEdge, ParallelEdge
│       │   ├── compiled.py       # CompiledGraph execution engine
│       │   ├── runner.py         # run() and run_sync() top-level functions
│       │   └── agent.py          # BaseAgent, DecoratedAgent, @agent decorator
│       ├── tools/                # Tool system
│       │   ├── __init__.py       # Re-exports ToolWrapper, tool, ToolRegistry
│       │   ├── base.py           # @tool decorator and ToolWrapper
│       │   └── registry.py       # ToolRegistry for centralized management
│       ├── providers/            # LLM provider adapters
│       │   ├── __init__.py       # Re-exports HttpProvider
│       │   └── http.py           # OpenAI-compatible HTTP provider
│       ├── observability/        # Logging, tracing, metrics
│       │   ├── __init__.py       # Re-exports setup_logging, get_logger
│       │   └── logging.py        # structlog configuration
│       ├── testing/              # Test utilities
│       │   ├── __init__.py       # Re-exports ScriptedLLM
│       │   └── scripted.py       # ScriptedLLM deterministic mock
│       └── cli/                  # CLI commands
│           ├── __init__.py       # Docstring only
│           └── main.py           # typer app: version, init, run
├── tests/                        # Test suite
│   ├── __init__.py
│   ├── conftest.py               # Shared fixtures (currently empty)
│   ├── test_smoke.py             # Import and scaffolding smoke tests
│   ├── unit/                     # Unit tests
│   │   ├── __init__.py
│   │   └── test_core.py          # Comprehensive core tests (530 lines)
│   └── fixtures/                 # Test fixtures
│       └── __init__.py
├── examples/                     # Usage examples
│   ├── sequential.py             # Sequential 3-node workflow
│   ├── parallel.py               # Fan-out/fan-in parallel workflow
│   ├── conditional.py            # Conditional routing workflow
│   └── handoff_basic.py          # Triage-to-specialist handoff pattern
├── planning/                     # Architecture and design documents
│   ├── API-DESIGN.md
│   ├── architecture-plan.md
│   ├── architecture-refinements.md
│   ├── PHASE1-PLAN.md
│   ├── RECONCILIATION.md
│   ├── ROADMAP.md
│   └── STRATEGIC-POSITIONING.md
├── research/                     # Deep research documents
│   ├── competitor-analysis.md
│   ├── domain-ecosystem.md
│   ├── implementation-patterns.md
│   ├── tech-stack-recommendation.md
│   ├── best-elements-synthesis.md
│   ├── a2a-protocol-and-governance.md
│   ├── cost-routing-algorithms.md
│   ├── evaluation-benchmarks.md
│   ├── mcp-security.md
│   ├── memory-architecture.md
│   └── SUMMARY.md
├── .github/
│   └── workflows/
│       └── ci.yml                # Lint, type-check, test matrix (3 OS x 3 Python)
├── .claude/                      # Claude agent configuration
│   ├── agent-memory/             # Per-agent memory stores
│   ├── agents/                   # Agent definitions
│   └── skills/                   # Reusable skill definitions
├── pyproject.toml                # Project config (hatchling build, deps, ruff, mypy, pytest)
├── Makefile                      # Dev commands: install, lint, fmt, type-check, test, clean
├── README.md                     # Project documentation
├── LICENSE                       # Apache-2.0
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
└── .gitignore
```

## Directory Purposes

**`src/orchestra/core/`:**
- Purpose: All core framework logic -- the heart of the engine
- Contains: Type definitions, protocol interfaces, state management, graph builder, execution engine, agent base classes, error hierarchy
- Key files: `types.py` (data models), `graph.py` (builder), `compiled.py` (runtime), `state.py` (state + reducers), `agent.py` (agent definitions)

**`src/orchestra/tools/`:**
- Purpose: Tool system for agent function-calling
- Contains: `@tool` decorator, `ToolWrapper` implementation, `ToolRegistry` for centralized tool management
- Key files: `base.py` (decorator + wrapper), `registry.py` (registry)

**`src/orchestra/providers/`:**
- Purpose: LLM provider adapters -- bridge between Orchestra and external LLM APIs
- Contains: Currently only `HttpProvider` for OpenAI-compatible endpoints
- Key files: `http.py` (generic HTTP provider with retry, error mapping, streaming)

**`src/orchestra/observability/`:**
- Purpose: Logging infrastructure
- Contains: `structlog` configuration for structured logging
- Key files: `logging.py` (setup and logger factory)

**`src/orchestra/testing/`:**
- Purpose: Test utilities shipped with the package for users to test their own workflows
- Contains: `ScriptedLLM` deterministic mock provider
- Key files: `scripted.py` (mock LLM with call logging and reset)

**`src/orchestra/cli/`:**
- Purpose: Command-line interface
- Contains: `typer` app with project scaffolding and workflow runner
- Key files: `main.py` (all CLI commands)

**`tests/`:**
- Purpose: Project test suite
- Contains: Smoke tests, unit tests organized by test class per concern
- Key files: `test_smoke.py` (import verification), `unit/test_core.py` (comprehensive core tests)

**`examples/`:**
- Purpose: Runnable example workflows demonstrating framework patterns
- Contains: Sequential, parallel, conditional, and handoff workflow patterns
- Key files: Each file is self-contained and runnable via `python examples/<name>.py`

**`planning/`:**
- Purpose: Historical architecture and design documents
- Contains: API design, phased plans, reconciliation docs, roadmap, strategic positioning

**`research/`:**
- Purpose: Deep research on competitor frameworks, ecosystem, implementation patterns
- Contains: Analysis of competing frameworks, domain ecosystem, best practices synthesis

## Key File Locations

**Entry Points:**
- `src/orchestra/__init__.py`: Package-level public API (what users import)
- `src/orchestra/cli/main.py`: CLI entry point (registered as `orchestra` console script)
- `src/orchestra/core/runner.py`: `run()` and `run_sync()` top-level execution functions

**Configuration:**
- `pyproject.toml`: Build system (hatchling), dependencies, tool config (ruff, mypy, pytest, coverage)
- `Makefile`: Developer workflow shortcuts
- `.github/workflows/ci.yml`: CI pipeline definition

**Core Logic:**
- `src/orchestra/core/graph.py`: Workflow graph builder (user-facing API)
- `src/orchestra/core/compiled.py`: Execution engine (runtime)
- `src/orchestra/core/state.py`: State management with reducers
- `src/orchestra/core/agent.py`: Agent definitions and tool-calling loop
- `src/orchestra/core/types.py`: All Pydantic data models
- `src/orchestra/core/protocols.py`: Protocol interfaces
- `src/orchestra/core/errors.py`: Error hierarchy

**Testing:**
- `tests/unit/test_core.py`: Primary test file (types, state, graph, execution, tools, agents, runner)
- `tests/test_smoke.py`: Import and scaffolding verification
- `tests/conftest.py`: Shared fixtures (currently empty -- for future use)
- `src/orchestra/testing/scripted.py`: `ScriptedLLM` mock (shipped with package)

## Naming Conventions

**Files:**
- Snake_case for all Python modules: `workflow_graph.py`, `base.py`, `scripted.py`
- Single-concept-per-file: `types.py`, `protocols.py`, `errors.py`, `state.py`, `context.py`, `nodes.py`, `edges.py`
- `__init__.py` in every package with explicit re-exports via `__all__`

**Directories:**
- Lowercase singular names: `core/`, `tools/`, `providers/`, `testing/`, `cli/`
- Test directories mirror purpose: `tests/unit/`, `tests/fixtures/`

**Classes:**
- PascalCase: `WorkflowGraph`, `CompiledGraph`, `BaseAgent`, `HttpProvider`, `ScriptedLLM`
- Suffix convention: `*Node` for graph nodes, `*Edge` for graph edges, `*Error` for exceptions

**Functions:**
- snake_case: `merge_list`, `apply_state_update`, `extract_reducers`
- Private methods prefixed with underscore: `_execute_node`, `_resolve_next`, `_handle_error_status`
- Reducer functions are bare names (no class): `merge_list`, `sum_numbers`, `keep_first`

**Type Aliases:**
- PascalCase: `GraphNode`, `GraphEdge`, `NodeFunction`, `EdgeCondition`
- Defined at module level using `=` assignment

**Constants:**
- UPPER_CASE: `END`, `START`
- Private sentinels with underscore prefix: `_EndSentinel`

## Where to Add New Code

**New LLM Provider (e.g., Anthropic, Google):**
- Implementation: `src/orchestra/providers/<provider_name>.py`
- Must satisfy the `LLMProvider` protocol from `src/orchestra/core/protocols.py`
- Re-export in: `src/orchestra/providers/__init__.py`
- Tests: `tests/unit/test_providers.py` (create this file)
- Reference implementation: `src/orchestra/providers/http.py`

**New Built-in Tool:**
- Implementation: `src/orchestra/tools/<tool_name>.py`
- Use the `@tool` decorator or implement the `Tool` protocol
- Re-export in: `src/orchestra/tools/__init__.py`
- Tests: `tests/unit/test_tools.py` (create this file)

**New State Reducer:**
- Add function in: `src/orchestra/core/state.py` (alongside existing 9 reducers)
- Signature: `def reducer_name(existing: T, new: T) -> T`
- Tests: Add to `TestState` class in `tests/unit/test_core.py`

**New Error Type:**
- Add class in: `src/orchestra/core/errors.py` under the appropriate category
- Re-export in: `src/orchestra/core/__init__.py`
- Follow pattern: inherit from category base (e.g., `GraphError`, `AgentError`)

**New Graph Node Type:**
- Add dataclass in: `src/orchestra/core/nodes.py`
- Add to `GraphNode` union type in same file
- Handle in `_wrap_as_node()` in `src/orchestra/core/graph.py`
- Handle in `_execute_node()` in `src/orchestra/core/compiled.py`

**New Graph Edge Type:**
- Add dataclass in: `src/orchestra/core/edges.py`
- Add to `GraphEdge` union type in same file
- Handle in `_resolve_next()` in `src/orchestra/core/compiled.py`

**New CLI Command:**
- Add `@app.command()` function in: `src/orchestra/cli/main.py`
- Use `typer` for argument parsing and `rich` for output formatting

**New Example Workflow:**
- Add file in: `examples/<pattern_name>.py`
- Make self-contained and runnable: include `if __name__ == "__main__": asyncio.run(main())`
- Follow pattern of existing examples (define state, define functions/agents, build graph, compile, run, print)

**New Test Module:**
- Add file in: `tests/unit/test_<module>.py`
- Use `pytest` with `@pytest.mark.asyncio` for async tests
- Organize by test class per concern (e.g., `TestTypes`, `TestState`, `TestGraph`)
- Use `ScriptedLLM` from `orchestra.testing` for agent tests

**New Observability Feature (tracing, metrics):**
- Add module in: `src/orchestra/observability/<feature>.py`
- Re-export in: `src/orchestra/observability/__init__.py`

## Special Directories

**`planning/`:**
- Purpose: Architecture design docs, roadmap, reconciliation notes
- Generated: No (human/AI authored)
- Committed: Yes

**`research/`:**
- Purpose: Deep research on domain, competitors, implementation patterns
- Generated: No (AI-authored research)
- Committed: Yes

**`.claude/`:**
- Purpose: Claude Code agent configuration, memory, and skill definitions
- Generated: Partially (memory is generated, skills are authored)
- Committed: Yes

**`__pycache__/` directories:**
- Purpose: Python bytecode cache
- Generated: Yes (automatically by Python)
- Committed: No (in `.gitignore`)

**`.pytest_cache/`, `.ruff_cache/`:**
- Purpose: Tool caches
- Generated: Yes
- Committed: No (in `.gitignore`)

---

*Structure analysis: 2026-03-07*
