# Codebase Concerns

**Analysis Date:** 2026-03-07

## Tech Debt

**Pervasive `Any` typing undermines type safety:**
- Issue: 145 occurrences of `Any` across 14 source files. Critical types like `AgentNode.agent`, `SubgraphNode.graph`, `ExecutionContext.provider`, `ExecutionContext.tool_registry`, and `GraphNode` fields are typed as `Any` rather than using the defined protocols (`Agent`, `LLMProvider`, `Tool`).
- Files: `src/orchestra/core/nodes.py` (lines 21, 57), `src/orchestra/core/context.py` (lines 32, 35), `src/orchestra/core/compiled.py` (line 71), `src/orchestra/core/graph.py` (lines 87-90, 350), `src/orchestra/core/runner.py` (lines 40-46)
- Impact: mypy strict mode passes vacuously on these boundaries. Users get no IDE autocompletion or type errors when passing wrong objects. Protocol types exist in `src/orchestra/core/protocols.py` but are never used as annotations in the actual implementation.
- Fix approach: Replace `Any` with the protocol types (`Agent`, `LLMProvider`, `Tool`) in dataclass/function signatures. Use `TYPE_CHECKING` imports to avoid circular imports where needed.

**Loop iteration counter uses closure with mutable state (non-reentrant):**
- Issue: `WorkflowGraph.loop()` at `src/orchestra/core/graph.py` line 335 creates a `nonlocal iteration_count` closure that persists across runs. The counter is never reset between invocations of `compiled.run()`, so the second execution of a compiled graph with a loop will have a stale counter and may terminate early or behave incorrectly.
- Files: `src/orchestra/core/graph.py` (lines 335-342)
- Impact: Any compiled graph using `.loop()` produces incorrect behavior after the first run. This is a functional bug disguised as tech debt.
- Fix approach: Move the iteration counter into runtime state (e.g., a special state field or context attribute) rather than a build-time closure. Alternatively, store per-run counters in `ExecutionContext`.

**Circular import workaround with late import:**
- Issue: `SubgraphNode` is imported after class definitions via a bare `from orchestra.core.nodes import SubgraphNode  # noqa: E402` to avoid a circular dependency between `graph.py` and `nodes.py`.
- Files: `src/orchestra/core/graph.py` (line 64)
- Impact: Fragile import order. If any other module tries to use `_wrap_as_node` before the import executes, it will fail with `NameError`. Also confusing for developers.
- Fix approach: Move `SubgraphNode` to a separate module, or restructure `_wrap_as_node` to use lazy isinstance checks.

**Silent structured output validation failure:**
- Issue: In `BaseAgent.run()`, when `output_type` is set and the LLM response fails Pydantic validation, the exception is silently caught and `structured_output` is set to `None` with no logging or warning.
- Files: `src/orchestra/core/agent.py` (lines 143-146)
- Impact: Users expect structured output but silently get `None` with no indication of what went wrong. Debugging this requires inspecting the raw output manually.
- Fix approach: Log a warning with the validation error. Consider raising `OutputValidationError` or at least populating an `errors` field on `AgentResult`.

**Silent structured output schema failure in provider:**
- Issue: In `HttpProvider.complete()`, if `output_type.model_json_schema()` fails, the exception is silently caught with a bare `except (AttributeError, Exception): pass`, and the request is sent without structured output formatting.
- Files: `src/orchestra/providers/http.py` (lines 147-158)
- Impact: User believes they requested structured output but the API call is sent without `response_format`, leading to unparseable responses that silently fail at the agent level too. Two silent failures compound.
- Fix approach: Log a warning. If schema generation fails, raise early rather than sending an unstructured request the user did not intend.

**`anyio` is a declared dependency but never used:**
- Issue: `anyio>=4.0` is listed in `pyproject.toml` dependencies but no source file imports it. The codebase uses `asyncio` directly everywhere.
- Files: `pyproject.toml` (line 33)
- Impact: Unnecessary dependency bloat. Misleads developers into thinking `anyio` is used for async compatibility.
- Fix approach: Remove `anyio` from dependencies, or migrate async primitives to `anyio` for trio compatibility (which was likely the original intent).

**`__node_execution_order__` injected into state dict as a side-channel:**
- Issue: `CompiledGraph.run()` injects `"__node_execution_order__"` into the returned state dict, and `runner.py` pops it out. This is a fragile convention using dunder-prefixed dict keys instead of a proper return type.
- Files: `src/orchestra/core/compiled.py` (line 152), `src/orchestra/core/runner.py` (line 93)
- Impact: If a user calls `compiled.run()` directly (bypassing `runner.run()`), they get a polluted state dict with metadata mixed into their domain state. If a state schema has strict validation, this could break.
- Fix approach: Return a structured result type from `CompiledGraph.run()` (e.g., `CompiledRunResult(state=..., execution_order=...)`) instead of mutating the state dict.

## Known Bugs

**Loop counter not reset between runs:**
- Symptoms: A compiled graph with `.loop()` works correctly on the first `run()` call but may terminate the loop prematurely or not at all on subsequent calls.
- Files: `src/orchestra/core/graph.py` (lines 335-342)
- Trigger: Call `compiled.run()` twice on a graph built with `.loop()`.
- Workaround: Recompile the graph before each run (`.compile()` creates new closures).

**Parallel state merge uses `object.__setattr__` to bypass frozen dataclass:**
- Symptoms: After parallel execution, state is mutated in-place using `object.__setattr__`, which violates the immutability contract of `WorkflowState` and can cause subtle bugs if the same state object is referenced elsewhere.
- Files: `src/orchestra/core/compiled.py` (lines 320-323)
- Trigger: Any workflow with `ParallelEdge` that uses `WorkflowState`.
- Workaround: None currently. The mutation is internal.

**`_parallel_nodes` attribute not always initialized:**
- Symptoms: If `.join()` is called without a preceding `.parallel()`, the code checks `hasattr(self, "_parallel_nodes")` which will be `False`, and the join node gets added but no edges connect the parallel branches to it.
- Files: `src/orchestra/core/graph.py` (lines 207-232)
- Trigger: Calling `.join()` without `.parallel()` in the fluent API.
- Workaround: Always use `.parallel()` before `.join()`. No validation error is raised.

## Security Considerations

**`eval()` usage in test code:**
- Risk: `eval(expression)` is used in a test tool definition at `tests/unit/test_core.py` line 494. While only in test code, this pattern could be copy-pasted into production tools by users following test examples.
- Files: `tests/unit/test_core.py` (line 494)
- Current mitigation: Only in test scope, not in library source.
- Recommendations: Replace with a safe math parser (e.g., `ast.literal_eval` or a simple calculator) in the test example to avoid setting a bad precedent.

**No tool execution sandboxing:**
- Risk: Tools execute arbitrary user-defined async functions with full Python access. A malicious or buggy tool can access the filesystem, network, or mutate shared state. There is no permission model, timeout enforcement, or isolation.
- Files: `src/orchestra/tools/base.py` (lines 109-133), `src/orchestra/core/agent.py` (lines 166-190)
- Current mitigation: Tool errors are caught and returned as `ToolResult` with `error` field. No sandboxing beyond that.
- Recommendations: Add configurable tool execution timeouts (using `asyncio.wait_for`). Consider a permission model using `ToolPermissionError` (which is defined in errors.py but never raised). Phase 2+ should add sandboxing.

**API key in memory without protection:**
- Risk: `HttpProvider` stores the API key as a plain string attribute `self._api_key`. It is readable by any code with a reference to the provider and could appear in tracebacks, logs, or serialized state.
- Files: `src/orchestra/providers/http.py` (line 99)
- Current mitigation: The key is prefixed with `_` (private convention). Not logged by structlog.
- Recommendations: Consider using `pydantic.SecretStr` or equivalent to prevent accidental logging/serialization. Override `__repr__` to redact.

**CLI `run` command executes arbitrary Python files:**
- Risk: `orchestra run workflow.py` uses `importlib` to execute arbitrary Python code. This is expected behavior for a CLI runner, but no sandboxing or validation is applied.
- Files: `src/orchestra/cli/main.py` (lines 86-109)
- Current mitigation: None. The tool is intended to run trusted local files.
- Recommendations: Document this as expected behavior. No sandboxing needed for a developer CLI tool, but add a note in docs.

## Performance Bottlenecks

**State serialization on every turn:**
- Problem: `CompiledGraph.run()` calls `state.model_dump()` twice per turn (once before node execution, once after for next-node resolution), and `apply_state_update` creates a full new state instance via `model_validate()` on every update.
- Files: `src/orchestra/core/compiled.py` (lines 124, 138), `src/orchestra/core/state.py` (lines 123-149)
- Cause: Immutable state pattern requires full serialization/deserialization round-trip on each state update.
- Improvement path: Use `model_copy(update=...)` instead of `model_dump()` + `model_validate()`. For read-only state access by nodes, pass a frozen view rather than serializing.

**No HTTP connection pooling strategy:**
- Problem: `HttpProvider` creates a single `httpx.AsyncClient` that is never closed unless the user explicitly calls `aclose()`. There is no context manager protocol, so resource cleanup is optional.
- Files: `src/orchestra/providers/http.py` (lines 102-106, 355-357)
- Cause: `HttpProvider` is not an async context manager. Users must remember to call `aclose()`.
- Improvement path: Implement `__aenter__`/`__aexit__` on `HttpProvider`. Alternatively, close the client in `CompiledGraph` teardown.

**Token counting is a rough heuristic:**
- Problem: `HttpProvider.count_tokens()` uses a `len(content) // 4 + 4` heuristic that can be off by 2-3x for non-English text or code.
- Files: `src/orchestra/providers/http.py` (lines 216-221)
- Cause: No tokenizer dependency (tiktoken) to keep the library lightweight.
- Improvement path: Add optional `tiktoken` dependency for accurate counting. Fall back to heuristic when not installed.

**Model cost table is hardcoded and will become stale:**
- Problem: `_MODEL_COSTS` dict in `HttpProvider` has hardcoded pricing for 5 models. New models and price changes require code changes.
- Files: `src/orchestra/providers/http.py` (lines 75-81)
- Cause: No external pricing data source.
- Improvement path: Move to a configuration file or allow runtime cost overrides. Consider fetching from a pricing API.

## Fragile Areas

**Fluent API state tracking (`_last_node`, `_parallel_nodes`):**
- Files: `src/orchestra/core/graph.py` (lines 158-346)
- Why fragile: The fluent API tracks builder state using `_last_node` and a dynamically-set `_parallel_nodes` attribute. Calling methods in the wrong order (e.g., `.join()` without `.parallel()`, `.branch()` without `.then()`) produces confusing behavior rather than clear errors. The `_parallel_nodes` attribute is created/deleted dynamically with `hasattr` checks.
- Safe modification: Always validate preconditions at the start of each fluent method. Use a proper state enum for the builder phase (e.g., SEQUENTIAL, PARALLEL_OPEN, BRANCHED).
- Test coverage: `.parallel()` + `.join()` has one test. `.branch()`, `.if_then()`, `.loop()` have zero execution tests.

**Agent input resolution in `_execute_agent_node`:**
- Files: `src/orchestra/core/compiled.py` (lines 199-263)
- Why fragile: The default input resolution logic has a multi-level fallback chain: `input_mapper` -> `messages` from state -> `input` from state -> `output` from state -> empty string. This implicit behavior is hard to predict and debug. The `agent_input` variable is re-assigned with a different type annotation (line 217: `Any`) in the middle of the block.
- Safe modification: Document the fallback chain. Consider making input resolution explicit (require `input_mapper` or fail with a clear error).
- Test coverage: Only tested via the full integration path, not in isolation.

**END sentinel comparison:**
- Files: `src/orchestra/core/compiled.py` (lines 108, 143-144), `src/orchestra/core/types.py` (lines 137-158)
- Why fragile: The codebase uses both `== END` and `is END` comparisons, plus `isinstance(current_node_id, type(END))` checks. The singleton pattern with `__eq__` override means `END == END` is `True` but `"END" == END` is `False`. Multiple comparison styles scattered across files make it easy to introduce bugs.
- Safe modification: Standardize on `is END` everywhere. Add a helper function `is_terminal(node_id)` that encapsulates the check.
- Test coverage: Sentinel tests exist in `tests/unit/test_core.py` but only test equality, not the comparison patterns used in `compiled.py`.

## Scaling Limits

**Single-process execution only:**
- Current capacity: All agent nodes execute in a single Python process using `asyncio.gather` for parallelism.
- Limit: CPU-bound tools or many concurrent agents will be bottlenecked by the GIL. No support for distributed execution.
- Scaling path: Phase 4 roadmap mentions Ray executor and NATS messaging. For now, parallel execution is I/O-bound only.

**No state persistence or checkpointing:**
- Current capacity: All state lives in memory for the duration of a run.
- Limit: Long-running workflows cannot survive process restarts. No resume capability.
- Scaling path: Phase 2 roadmap includes event-sourced persistence and time-travel debugging.

**No rate limiting or concurrency control:**
- Current capacity: Parallel edges fire all tasks simultaneously with no concurrency limit.
- Limit: A graph with 20 parallel nodes will make 20 simultaneous API calls, likely hitting rate limits.
- Scaling path: Add a semaphore-based concurrency limiter to `_execute_parallel`. The retry logic in `HttpProvider` handles rate limits reactively but not proactively.

## Dependencies at Risk

**None currently critical**, but notable:
- `structlog>=24.0`: Pinned to a fairly recent version. The structlog API has been stable, but the minimum version is aggressive for a library.
- `typer>=0.12`: Typer is in active development. The CLI is simple enough to be compatible, but breaking changes in Typer's argument parsing could affect the CLI.
- `httpx>=0.26`: Core dependency for the only production LLM provider. httpx is stable and well-maintained.

## Missing Critical Features

**No Anthropic or Google provider implementations:**
- Problem: `pyproject.toml` declares optional dependencies for `anthropic` and `google-generativeai`, but no provider implementations exist. Only `HttpProvider` (OpenAI-compatible) is implemented.
- Blocks: Users cannot use Claude or Gemini models without writing their own provider or routing through an OpenAI-compatible proxy.
- Files: `src/orchestra/providers/__init__.py` (only exports `HttpProvider`)

**No agent timeout enforcement:**
- Problem: `AgentTimeoutError` is defined in `src/orchestra/core/errors.py` but never raised anywhere. There is no timeout mechanism for agent execution.
- Blocks: Runaway agents (infinite tool loops below `max_iterations`, slow LLM calls) cannot be interrupted.
- Files: `src/orchestra/core/errors.py` (line 43), `src/orchestra/core/agent.py` (no timeout logic)

**No handoff protocol:**
- Problem: `AgentResult.handoff_to` field exists (`src/orchestra/core/types.py` line 78) but is never read or acted upon by the execution engine. Agents cannot hand off to other agents mid-execution.
- Blocks: The Swarm-style handoff pattern demonstrated in `examples/handoff_basic.py` uses conditional edges as a workaround, not true agent-initiated handoffs.
- Files: `src/orchestra/core/types.py` (line 78), `src/orchestra/core/compiled.py` (never reads `handoff_to`)

**No streaming support in the execution engine:**
- Problem: `HttpProvider.stream()` is implemented, `StreamChunk` type exists, and `LLMProvider` protocol defines `stream()`, but the agent run loop (`BaseAgent.run()`) and execution engine (`CompiledGraph`) only use `complete()`. There is no way to stream responses through the graph.
- Blocks: Real-time UIs, progressive output, and long-form generation use cases.
- Files: `src/orchestra/core/agent.py` (only calls `llm.complete()`), `src/orchestra/core/compiled.py` (no streaming path)

**ToolRegistry is disconnected from agent execution:**
- Problem: `ToolRegistry` exists in `src/orchestra/tools/registry.py` and `ExecutionContext` has a `tool_registry` field, but agents look up tools from their own `self.tools` list, not from the registry. The registry is never populated or consulted during execution.
- Blocks: Centralized tool management, dynamic tool registration, and tool permission enforcement.
- Files: `src/orchestra/tools/registry.py`, `src/orchestra/core/context.py` (line 35), `src/orchestra/core/agent.py` (line 172 - searches `self.tools`)

## Test Coverage Gaps

**No tests for fluent `.branch()`, `.if_then()`, or `.loop()` execution:**
- What's not tested: The fluent API branching, conditional if/then, and loop methods have zero execution tests. Only `.then()` and explicit API conditional/parallel edges are tested.
- Files: `src/orchestra/core/graph.py` (lines 234-346)
- Risk: These methods contain subtle logic (closure-based loop counter, dynamic attribute management) that could silently break.
- Priority: High

**No tests for `HttpProvider`:**
- What's not tested: The entire HTTP provider including retry logic, error handling, response parsing, streaming, and token counting.
- Files: `src/orchestra/providers/http.py` (all 357 lines)
- Risk: The only production LLM provider has zero test coverage. Any bug in retry logic, error mapping, or response parsing would go undetected.
- Priority: High

**No tests for `SubgraphNode` execution:**
- What's not tested: Subgraph composition (nesting a compiled graph inside another graph).
- Files: `src/orchestra/core/nodes.py` (lines 53-64), `src/orchestra/core/compiled.py` (line 184)
- Risk: Subgraph input/output mapping, state isolation, and error propagation are untested.
- Priority: Medium

**No tests for CLI commands:**
- What's not tested: `orchestra version`, `orchestra init`, and `orchestra run` commands.
- Files: `src/orchestra/cli/main.py` (all 113 lines)
- Risk: CLI scaffold generation or workflow execution could break without detection.
- Priority: Medium

**No tests for `to_mermaid()` output correctness:**
- What's not tested: The Mermaid diagram generator is tested for basic string inclusion but not for structural correctness (valid Mermaid syntax, correct edge representation).
- Files: `src/orchestra/core/compiled.py` (lines 328-373)
- Risk: Low -- visualization feature, not core functionality.
- Priority: Low

**Empty `conftest.py` and `fixtures/` directory:**
- What's not tested: No shared fixtures exist despite the fixture directory being created.
- Files: `tests/conftest.py` (1 line -- just a docstring), `tests/fixtures/__init__.py`
- Risk: Each test reinvents setup patterns. As tests grow, duplication will increase.
- Priority: Low

---

*Concerns audit: 2026-03-07*
