---
phase: "02-differentiation"
plan: "04b"
subsystem: "observability + handoff-protocol"
tags: ["trace-renderer", "rich", "handoff", "context-distillation", "event-bus"]
dependency_graph:
  requires: ["01-event-bus", "02-04a-sqlite-store"]
  provides: ["rich-trace-renderer", "handoff-edge", "context-distill", "llm-tool-events"]
  affects: ["compiled-graph", "base-agent", "workflow-graph"]
tech_stack:
  added: ["rich.tree", "rich.live", "dataclasses.frozen"]
  patterns: ["eventbus-subscriber", "three-zone-distillation", "swarm-handoff"]
key_files:
  created:
    - src/orchestra/observability/console.py
    - src/orchestra/core/handoff.py
    - src/orchestra/core/context_distill.py
    - tests/unit/test_trace.py
    - tests/unit/test_handoff.py
  modified:
    - src/orchestra/core/compiled.py
    - src/orchestra/core/agent.py
    - src/orchestra/core/graph.py
decisions:
  - "HandoffPayload uses tuple fields (conversation_history, metadata) to satisfy frozen=True dataclass; .create() factory accepts mutable Python types and converts"
  - "RichTraceRenderer._live set to None on terminal failure so stop() is always safe to call"
  - "agent.py LLM/tool emission uses getattr(context, 'replay_mode', False) so replay_mode field can be added later without breaking current callers"
  - "distill_context middleware summary wraps content in '[Context summary: ...]' assistant message to signal to the receiving agent that history was compressed"
metrics:
  duration: "~2 hours"
  completed_date: "2026-03-09"
  tasks_completed: 5
  tasks_total: 5
  files_created: 5
  files_modified: 3
  tests_added: 45
  tests_baseline: 174
  tests_final: 219
---

# Phase 02 Plan 04b: Rich Trace Renderer + Handoff Protocol Summary

**One-liner:** Real-time Rich terminal trace rendering via EventBus subscription, plus Swarm-style HandoffEdge with three-zone context distillation.

## What Was Built

### Task 4b.1 - RichTraceRenderer (`src/orchestra/observability/console.py`)

EventBus subscriber that renders a live-updating terminal tree at 4fps. Maps all workflow events to tree nodes:

- `ExecutionStarted` → root label `Workflow: {name}`
- `NodeStarted` → dim branch `{node_id} ...`
- `LLMCalled` → leaf with tokens, cost, duration; accumulates totals
- `ToolCalled` → cyan leaf with args/result (truncated to 50 chars in normal mode, 200 in verbose)
- `NodeCompleted` → updates branch label to `✓ {node_id} [{s}s] {tok} tok ${cost}`
- `ExecutionCompleted` → adds `TOTAL:` or `FAILED` summary line

Controlled by `ORCHESTRA_TRACE` (off / rich / verbose) and `ORCHESTRA_ENV`. Gracefully degrades if no terminal available — `Live.start()` failure sets `_live=None` and all further operations are no-ops.

### Task 4b.2 - Trace wiring in CompiledGraph.run() (`src/orchestra/core/compiled.py`)

After the SQLite subscriber is registered, the trace renderer is subscribed when `ORCHESTRA_TRACE != off`. Renderer is started before `ExecutionStarted` is emitted and stopped in both the success and error paths.

### Task 4b.3 - LLM/Tool event emission from BaseAgent.run() (`src/orchestra/core/agent.py`)

`BaseAgent.run()` now emits `LLMCalled` after each LLM completion and `ToolCalled` after each tool execution. Both guards check `context.event_bus is not None` and `getattr(context, 'replay_mode', False)`. Token counts, cost (from `estimated_cost_usd`), and wall-clock duration are included. Fully backwards compatible — no-op when event_bus is absent.

### Task 4b.4 - Handoff Protocol

**`src/orchestra/core/handoff.py`**
- `HandoffEdge(source, target, condition, distill)` — frozen dataclass, first-class edge type
- `HandoffPayload` — frozen dataclass carrying conversation history and metadata; uses tuples internally for immutability, `.create()` factory accepts mutable lists/dicts

**`src/orchestra/core/context_distill.py`**
- `distill_context()` — three-zone partitioning: system prefix (intact) + middleware summary (word-truncated to `max_middleware_tokens`) + last N turns suffix (intact)
- `full_passthrough()` — identity function for `distill=False` handoffs

**`src/orchestra/core/graph.py`**
- `WorkflowGraph.add_handoff(from_agent, to_agent, *, condition, distill)` — fluent API, stores `HandoffEdge` in `_handoff_edges`, passed through to `CompiledGraph` via `compile()`

### Task 4b.5 - Tests

- `tests/unit/test_trace.py` — 18 tests: instantiation, all event handlers, lifecycle, verbose truncation, token accumulation
- `tests/unit/test_handoff.py` — 27 tests: `add_handoff()`, frozen dataclasses, `distill_context` three zones, `full_passthrough`, conditional edges, `HandoffPayload`

## Test Results

| Suite | Tests | Result |
|-------|-------|--------|
| test_trace.py | 18 | PASS |
| test_handoff.py | 27 | PASS |
| All unit tests (regression) | 219 | PASS |

Baseline was 174 tests. This plan added 45.

## Commits

| Hash | Message |
|------|---------|
| af9ddc1 | feat(02-04b): add RichTraceRenderer EventBus subscriber |
| 2892bf3 | feat(02-04b): wire RichTraceRenderer into CompiledGraph.run() |
| 7a3f2bc | feat(02-04b): emit LLMCalled and ToolCalled events from BaseAgent.run() |
| 34921c3 | feat(02-04b): add HandoffEdge, HandoffPayload, context distillation, add_handoff() |
| 5523205 | test(02-04b): add 45 tests for trace renderer and handoff protocol |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Design] HandoffPayload frozen dataclass field types**

- **Found during:** Task 4b.4
- **Issue:** `frozen=True` dataclasses do not allow `list` or `dict` fields because they are mutable and violate hashability. `conversation_history: list[Message]` and `metadata: dict[str, Any]` would raise `TypeError` on construction.
- **Fix:** Changed fields to `tuple[Any, ...]` and `tuple[tuple[str, Any], ...]` respectively. Added a `.create()` classmethod that accepts the mutable types callers expect and converts them internally. Added `.metadata_dict()` and `.history_list()` convenience accessors.
- **Files modified:** `src/orchestra/core/handoff.py`
- **Commit:** 34921c3

**2. [Rule 2 - Completeness] replay_mode not yet on ExecutionContext**

- **Found during:** Task 4b.3
- **Issue:** The plan mentioned `context.replay_mode` but the field does not exist on `ExecutionContext` yet (Plan 07 deliverable).
- **Fix:** Used `getattr(context, 'replay_mode', False)` so the guard works today and will automatically pick up the real field when Plan 07 adds it.
- **Files modified:** `src/orchestra/core/agent.py`
- **Commit:** 7a3f2bc

## Self-Check: PASSED

Files verified present:
- `src/orchestra/observability/console.py` FOUND
- `src/orchestra/core/handoff.py` FOUND
- `src/orchestra/core/context_distill.py` FOUND
- `tests/unit/test_trace.py` FOUND
- `tests/unit/test_handoff.py` FOUND

Commits verified in git log:
- af9ddc1 FOUND
- 2892bf3 FOUND
- 7a3f2bc FOUND
- 34921c3 FOUND
- 5523205 FOUND
