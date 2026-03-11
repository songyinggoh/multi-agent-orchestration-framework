# Phase 3: Production Readiness — Implementation Research

**Phase:** 3 - Production Readiness
**Confidence:** HIGH
**Date:** 2026-03-10

---

## 1. FastAPI Server (3.1)

### Integration Points
- `CompiledGraph.run()` is fully async with EventBus — FastAPI wrapping is straightforward
- Method accepts `input`, `provider`, `event_store`, `run_id` directly, mapping cleanly to REST endpoint parameters
- `CompiledGraph.resume()` maps to `POST /runs/{id}/resume`
- Graph lifecycle: load/compile graphs on startup or dynamically via a registry

### Streaming
- Use `sse-starlette` for SSE streaming — W3C-compliant, 200K+ weekly downloads, native async support
- Stream workflow events from EventBus through an `asyncio.Queue` to the SSE response
- Pattern: EventBus subscriber pushes events to queue → SSE endpoint yields from queue

### Recommended Stack
- `fastapi` + `uvicorn[standard]` for ASGI
- `sse-starlette` for Server-Sent Events
- `pydantic` v2 for request/response models (already a dependency)

### Key Design Decisions
- Graph Registry: how graphs are loaded/registered at server startup (config file vs dynamic registration)
- Run isolation: each run gets its own EventBus instance (already the case in `CompiledGraph.run()`)
- Error handling: map Orchestra exceptions to HTTP status codes

---

## 2. OpenTelemetry Integration (3.2)

### Architecture
- OTel is a **third EventBus subscriber** (alongside RichTraceRenderer and EventStore)
- Same subscription pattern used by `RichTraceRenderer` in `console.py`
- No core engine changes needed

### Span Mapping
| Orchestra Event | OTel Span |
|----------------|-----------|
| `ExecutionStarted` | Root span: `graph.run` |
| `NodeStarted` → `NodeCompleted` | Child span: `node.{name}` |
| `LLMCalled` | Child span: `llm.{model}` with token attributes |
| `ToolCalled` | Child span: `tool.{name}` |
| `ErrorOccurred` | Span status ERROR + exception recording |

### Attributes (emerging LLM observability standards)
- `gen_ai.system` — provider name
- `gen_ai.request.model` — model identifier
- `gen_ai.usage.input_tokens` — prompt tokens
- `gen_ai.usage.output_tokens` — completion tokens
- `gen_ai.response.finish_reason` — stop reason

### Gap: Parallel Context Propagation
- `asyncio.gather` in `_execute_parallel` doesn't automatically propagate OTel context
- Fix: wrap each parallel task with `opentelemetry.context.attach(opentelemetry.context.get_current())`
- This is a known pattern — ~3 lines per parallel execution site

### Recommended Stack
- `opentelemetry-sdk` 1.40+
- `opentelemetry-instrumentation-fastapi` for auto HTTP tracing
- `opentelemetry-exporter-otlp` for Jaeger/Tempo/Zipkin
- Docker Compose with Jaeger for local dev visualization

---

## 3. Caching Layer (3.3)

### Key Finding: Redis is Premature for Phase 3
- No distributed deployment exists until Phase 4 (Ray executor, NATS)
- For single-process deployment, in-process caching delivers identical value
- Redis adds infrastructure cost, connection pool management, serialization overhead

### Recommended: CachedProvider Pattern
```python
class CachedProvider:
    """Wraps LLMProvider with cache-through. ~50 lines."""
    def __init__(self, provider: LLMProvider, cache: CacheBackend): ...
    async def complete(self, messages, **kwargs) -> LLMResponse:
        key = self._cache_key(messages, kwargs)
        if cached := await self.cache.get(key):
            return cached
        result = await self.provider.complete(messages, **kwargs)
        await self.cache.set(key, result)
        return result
```

### Cache Key Strategy
- SHA-256 fingerprint of `(model, messages, temperature, max_tokens)`
- Only cache `temperature=0` (deterministic) calls by default
- TTL-based expiration (configurable, default 1 hour)

### Backend Options (Phase 3)
| Backend | Infra | Persistence | Speed | Recommendation |
|---------|-------|-------------|-------|---------------|
| `cachetools.TTLCache` | None | No | Fastest | Default for dev/single-process |
| `diskcache.Cache` | None | Yes (file-based) | Fast | For persistence across restarts |

### Phase 4 Upgrade Path
- Design a `CacheBackend` protocol so Redis can swap in mechanically (~30 lines)
- `RedisCacheBackend` becomes a Phase 4 addition when distributed deployment exists

---

## 4. Multi-Tier Memory (3.4)

### Key Finding: Defer Full Implementation to Phase 4
- Full vector-search memory tiering is Phase 4 material (alongside dynamic subgraphs)
- What Phase 3 needs: a `MemoryManager` protocol stub defining the interface
- Active run state already lives in EventStore (SQLite/Postgres) — no new storage needed
- Old runs queryable via `list_runs()` — already implemented

### Phase 3 Scope (Thin Interface Only)
```python
class MemoryManager(Protocol):
    async def store(self, key: str, value: Any, tier: Literal["hot", "cold"]) -> None: ...
    async def retrieve(self, key: str) -> Any | None: ...
    async def promote(self, key: str) -> None: ...  # cold → hot
    async def demote(self, key: str) -> None: ...   # hot → cold
```

### Deferred to Phase 4
- Redis as hot tier storage
- Vector similarity retrieval from cold tier
- Automatic promotion/demotion based on recency/relevance
- Embedding-based semantic retrieval

---

## 5. Guardrails (3.5)

### Key Finding: Build Custom, Don't Import Frameworks

**Why not NeMo Guardrails:** colang DSL is architecturally incompatible with graph-based execution. Imposes its own conversation model.

**Why not Guardrails AI:** Pulls in OpenAI SDK, litellm, many transitive dependencies. Structured output validation already handled by `LLMProvider.complete(output_type=...)` via Pydantic.

### Recommended: Custom GuardrailMiddleware (~150 lines)
```python
# src/orchestra/security/guardrails.py

class InputValidator(Protocol):
    async def validate(self, state: dict) -> ValidationResult: ...

class OutputValidator(Protocol):
    async def validate(self, result: AgentResult) -> ValidationResult: ...

class ValidationResult(BaseModel):
    passed: bool
    violations: list[str] = []
    action: Literal["allow", "retry", "fallback", "refuse"] = "allow"
```

### Integration Points
- **Input guards:** Use existing node factory pattern (`make_injection_guard_node` from Rebuff)
- **Output guards:** Add optional `output_validators: list[Callable]` hook to `_execute_agent_node` in `compiled.py`
- **Events:** Emit `SecurityViolation` for input failures, `OutputRejected` for output failures (both already exist)

### Architectural Change Required
One additive change to `compiled.py`: output validator hook in `_execute_agent_node`. This is surgical, not structural.

---

## 6. Cost Tracking (3.6)

### Key Finding: Collection is Solved; Aggregation is the Task

**Already captured in `LLMCalled` events (agent.py lines 115-136):**
- `input_tokens`, `output_tokens`, `cost_usd`, `duration_ms`, `model`

**Already captured in `ExecutionCompleted` events:**
- `total_tokens`, `total_cost_usd` (currently default to 0 — need wiring)

### Implementation Plan
1. **CostAggregator** — EventBus subscriber that accumulates per-run costs from `LLMCalled` events
2. **Budget limits** — soft warnings + hard limits per run, configurable via `RunRequest`
3. **tiktoken integration** — for providers that don't return token usage in responses
4. **Cost field in API response** — aggregate from `ExecutionCompleted` event
5. **Model cost registry** — centralized pricing table (partially exists in providers)

### Token Counting
- Most providers return usage in response (OpenAI, Anthropic, Google)
- Ollama may not — use `tiktoken` as fallback counter
- `tiktoken` is lightweight, well-maintained, covers GPT-family tokenizers

---

## 7. Advanced Testing (3.7)

### Existing Test Infrastructure
- 244 unit tests passing
- `ScriptedLLM` in testing helpers for deterministic responses
- EventStore protocol conformance suites

### Phase 3 Testing Additions
1. **Concurrency tests** — verify thread safety of parallel graph execution via `_execute_parallel`
2. **Fault injection** — decorate Provider calls with random timeouts/errors during test runs
3. **E2E regression suite** — test against FastAPI endpoints with `httpx.AsyncClient`
4. **SSE stream testing** — verify event ordering and completeness

### Recommended Tools
- `locust` or `k6` for load testing the FastAPI server
- `pytest-asyncio` (already used) for async test patterns
- `httpx` for async API testing (built into FastAPI test utilities)

### Chaos Testing Scope (Phase 3)
- Provider timeout simulation only
- Database connection failure recovery
- Do NOT attempt distributed chaos (no distributed deployment yet)

---

## Open Questions

1. **Graph Registry design** — how graphs are loaded/registered at server startup
2. **Multi-tier memory scope** — defer full implementation, keep thin interface
3. **Semantic caching** — defer to Phase 4, use exact SHA-256 match for Phase 3

---

## Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Standard Stack (FastAPI, OTel) | HIGH | Mature libraries, well-documented, widely used |
| Architecture Integration | HIGH | Integration points identified from codebase source analysis |
| Pitfalls | HIGH | Derived from actual codebase structure (EventBus, async patterns) |
| Guardrails Design | MEDIUM-HIGH | Custom Protocol approach aligned with codebase patterns |
| Memory Architecture | MEDIUM | Deferred to Phase 4 — thin stub is low-risk |

**Ready for planning.**
