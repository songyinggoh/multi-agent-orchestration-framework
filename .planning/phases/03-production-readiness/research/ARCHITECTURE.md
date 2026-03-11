# Architecture Patterns — Phase 3: Production Readiness

**Domain:** Agent orchestration framework — production serving layer
**Researched:** 2026-03-10

## Recommended Architecture

### High-Level Layer Diagram

```
                      CLIENT (curl, browser, service)
                             |
                    [FastAPI + SSE Transport]
                      |              |
                 [OTel Middleware]  [Auth Middleware]
                      |
                [Run Manager]  ---- manages lifecycle of runs
                      |
                [CompiledGraph]  -- existing orchestration engine
                   /     \
            [Nodes]     [Edges]
               |
         [LLM Provider]
           /        \
    [Cache Layer]   [Guardrails]
    (Redis)         (pre/post hooks)
         \          /
      [Cost Tracker]
      (token counting + OTel metrics)
```

### Component Boundaries

| Component | Responsibility | Communicates With | New/Existing |
|-----------|---------------|-------------------|--------------|
| FastAPI App (`server/app.py`) | HTTP transport, SSE streaming, request/response serialization | Run Manager | NEW |
| Run Manager (`server/runs.py`) | Lifecycle management: create, track, cancel, resume runs. Decouples HTTP request from graph execution. | CompiledGraph, EventStore | NEW |
| OTel Tracer (`observability/tracing.py`) | Span creation for graph/node/LLM layers, context propagation | All components (cross-cutting) | NEW |
| Cache Layer (`cache/redis.py`) | LLM response caching (exact-match, optionally semantic) | LLM Providers, Redis | NEW |
| Memory Manager (`memory/manager.py`) | Hot/cold tier promotion/demotion, unified retrieval interface | Redis (hot), SQLite/Postgres (cold) | NEW |
| Guardrail Runner (`security/guardrails.py`) | Pre/post validation hooks on node execution | Existing ContractRegistry, Guardrails AI validators | NEW (extends existing) |
| Cost Tracker (`observability/cost.py`) | Token counting, cost calculation, budget enforcement | LLM Providers, OTel metrics, EventStore | NEW |
| CompiledGraph | Orchestration engine — unchanged | Nodes, Edges, EventStore | EXISTING |
| EventStore | Event-sourced persistence — unchanged | SQLite, PostgreSQL | EXISTING |
| LLM Providers | Provider adapters — extended with cache + cost hooks | External LLM APIs | EXISTING (extended) |

### Data Flow

**Standard run (POST /runs):**
```
1. Client sends POST /runs with RunRequest (graph name, initial state, config)
2. FastAPI validates via Pydantic, creates OTel root span
3. Run Manager creates run_id, stores in registry, starts async task
4. CompiledGraph.run() executes:
   a. Each node creates child OTel span
   b. LLM calls check Cache Layer first
      - Cache HIT: return cached response, emit cache.hit metric
      - Cache MISS: call provider, cache response, emit cache.miss metric
   c. Guardrails validate LLM output before state update
   d. Cost Tracker records tokens + cost per LLM call
   e. Events emitted to EventStore as usual
5. Run Manager marks run complete, stores final state
6. Response returned with run_id, final state, cost summary
```

**Streaming run (GET /runs/{id}/stream):**
```
1. Client opens SSE connection
2. Run Manager looks up active run (or starts new one)
3. EventSourceResponse yields events as they occur:
   - node.started, node.completed (progress)
   - llm.token (individual tokens for streaming)
   - run.completed (final event, closes stream)
4. Client disconnect detected by sse-starlette, cancellation propagated
```

**HITL resume (POST /runs/{id}/resume):**
```
1. Client sends resume payload (approval, edited state)
2. Run Manager looks up interrupted run
3. CompiledGraph.resume() called with checkpoint
4. Execution continues from interrupt point
5. Response includes remaining execution results
```

## Patterns to Follow

### Pattern 1: Run Manager (Decoupled Lifecycle)

**What:** A RunManager class that tracks active runs independently of HTTP requests. Runs are started as background asyncio tasks and their status is queryable via run_id.

**When:** Always. This is the central pattern that prevents coupling HTTP lifecycle to agent lifecycle.

**Why:** HITL runs can be interrupted for hours or days. Server restarts should not lose run state. Multiple HTTP requests interact with the same run (start, stream, resume, cancel).

**Example:**
```python
class RunManager:
    """Manages the lifecycle of agent runs independently of HTTP requests."""

    def __init__(self, event_store: EventStore):
        self._active_runs: dict[str, RunHandle] = {}
        self._event_store = event_store

    async def create_run(
        self, graph: CompiledGraph, initial_state: dict, config: RunConfig
    ) -> str:
        run_id = uuid.uuid4().hex
        handle = RunHandle(run_id=run_id, graph=graph, state=initial_state)
        self._active_runs[run_id] = handle
        handle.task = asyncio.create_task(self._execute(handle, config))
        return run_id

    async def get_status(self, run_id: str) -> RunStatus:
        handle = self._active_runs.get(run_id)
        if handle:
            return handle.status
        # Check event store for completed/interrupted runs
        return await self._event_store.get_run_status(run_id)

    async def subscribe_events(self, run_id: str) -> AsyncIterator[WorkflowEvent]:
        """Yield events as they occur for SSE streaming."""
        handle = self._active_runs.get(run_id)
        if handle is None:
            raise RunNotFoundError(run_id)
        async for event in handle.event_queue:
            yield event
```

### Pattern 2: Cache-Through Provider Decorator

**What:** A decorator or wrapper around LLMProvider.chat() that transparently checks Redis before making an API call.

**When:** For deterministic or near-deterministic calls (temperature=0, same prompt). Skip caching for high-temperature creative generation.

**Example:**
```python
class CachedProvider:
    """Wraps an LLMProvider with transparent Redis caching."""

    def __init__(self, provider: LLMProvider, cache: LLMCache):
        self._provider = provider
        self._cache = cache

    async def chat(self, messages: list[dict], **kwargs) -> LLMResponse:
        if kwargs.get("temperature", 1.0) > 0:
            return await self._provider.chat(messages, **kwargs)

        cache_key = self._build_key(messages, kwargs)
        cached = await self._cache.get(cache_key)
        if cached:
            return cached

        response = await self._provider.chat(messages, **kwargs)
        await self._cache.set(cache_key, response, ttl=3600)
        return response
```

### Pattern 3: OTel Span Hierarchy

**What:** Three-tier span hierarchy: HTTP request > graph run > node execution > LLM call. Each level adds relevant attributes from the GenAI semantic conventions.

**When:** Always. This is the observability backbone.

**Span attribute mapping (per OTel GenAI semconv v1.37+):**
```python
# Graph run span
span.set_attribute("gen_ai.operation.name", "orchestrate")
span.set_attribute("orchestra.graph.name", graph.name)
span.set_attribute("orchestra.run.id", run_id)

# Node execution span (child of graph run)
span.set_attribute("orchestra.node.name", node.name)
span.set_attribute("orchestra.node.type", "agent" | "function" | "subgraph")

# LLM call span (child of node execution)
span.set_attribute("gen_ai.system", "openai")  # or "anthropic", "google"
span.set_attribute("gen_ai.request.model", "gpt-4o")
span.set_attribute("gen_ai.usage.input_tokens", prompt_tokens)
span.set_attribute("gen_ai.usage.output_tokens", completion_tokens)
span.set_attribute("gen_ai.response.model", actual_model_used)
```

### Pattern 4: Guardrails as Node Hooks

**What:** Extend the existing `ContractRegistry` pattern to support pre-execution and post-execution validators, not just output schema validation.

**When:** For any node that processes untrusted input or produces user-facing output.

**Example:**
```python
class GuardrailRunner:
    """Executes pre/post validators on node I/O."""

    def __init__(self, registry: ContractRegistry):
        self._registry = registry
        self._pre_validators: dict[str, list[Validator]] = {}
        self._post_validators: dict[str, list[Validator]] = {}

    def add_pre_validator(self, node_name: str, validator: Validator) -> None:
        self._pre_validators.setdefault(node_name, []).append(validator)

    async def run_pre(self, node_name: str, input_data: dict) -> ValidationResult:
        for v in self._pre_validators.get(node_name, []):
            result = await v.validate(input_data)
            if not result.is_valid:
                return result  # fail-fast
        return ValidationResult(is_valid=True)
```

### Pattern 5: Cost Tracking as Cross-Cutting Concern

**What:** Token counting and cost calculation happen at the LLM provider boundary. Costs are recorded both in the EventStore (for per-run attribution) and as OTel metrics (for dashboards and alerting).

**When:** Every LLM call. No exceptions.

**Example:**
```python
class CostTracker:
    """Tracks token usage and cost per LLM call."""

    def __init__(self, pricing: dict[str, ModelPricing], meter: Meter):
        self._pricing = pricing
        self._cost_counter = meter.create_counter(
            "gen_ai.usage.cost",
            unit="USD",
            description="Cost of LLM API calls",
        )
        self._token_counter = meter.create_counter(
            "gen_ai.usage.tokens",
            unit="token",
            description="Tokens consumed by LLM API calls",
        )

    def record(self, model: str, input_tokens: int, output_tokens: int,
               run_id: str, node_name: str) -> float:
        pricing = self._pricing.get(model)
        cost = (input_tokens * pricing.input_cost_per_token +
                output_tokens * pricing.output_cost_per_token)
        attributes = {
            "gen_ai.request.model": model,
            "orchestra.run.id": run_id,
            "orchestra.node.name": node_name,
        }
        self._cost_counter.add(cost, attributes)
        self._token_counter.add(input_tokens + output_tokens, attributes)
        return cost
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Synchronous Graph Execution in Request Handler

**What:** Running `await graph.run()` directly inside a FastAPI route handler.

**Why bad:** If the graph takes 30 seconds and the HTTP client disconnects at second 5, the run may be cancelled. With HITL, runs can be interrupted for hours — no HTTP connection should be held that long.

**Instead:** Use the RunManager pattern. Route handlers create runs and return run_ids. Streaming endpoints subscribe to events. The graph execution is a background task.

### Anti-Pattern 2: Caching All LLM Calls Indiscriminately

**What:** Caching responses for all LLM calls regardless of temperature or context.

**Why bad:** High-temperature calls (temperature > 0) are intentionally non-deterministic. Caching them returns stale creative output. Calls with dynamic context (e.g., current time, user-specific data) produce misleading cache hits.

**Instead:** Only cache calls where temperature=0. Include all relevant parameters (model, messages, tools, system prompt) in the cache key. Provide a `cacheable=False` flag for calls that should never be cached.

### Anti-Pattern 3: Monolithic OTel Spans

**What:** Creating a single span for the entire graph run with all attributes crammed in.

**Why bad:** Loses the ability to pinpoint which node or LLM call is slow. Cannot identify cost hotspots. No parent-child relationship means no waterfall view in Jaeger.

**Instead:** Three-tier hierarchy (graph > node > LLM call) with each span carrying only its own attributes. Use span events (not attributes) for large data like prompts and completions (per v1.38.0 conventions).

### Anti-Pattern 4: Guardrails That Silently Swallow Failures

**What:** Guardrail violations that return a default value without logging or alerting.

**Why bad:** In production, silent failures mask systemic issues. A guardrail firing 50% of the time indicates a prompt engineering problem that needs attention, not silent fallbacks.

**Instead:** Always emit an OTel event/metric when a guardrail fires. Provide configurable strategies: `raise` (fail the node), `retry` (re-prompt with feedback), `fallback` (use a default, but log it), `warn` (continue but emit a warning metric).

### Anti-Pattern 5: Redis as Required Dependency

**What:** Making Redis a hard requirement so Orchestra cannot start without it.

**Why bad:** Breaks local development, testing, and minimal deployments. Users evaluating Orchestra should not need to run Redis.

**Instead:** Redis operations must be fail-open. If Redis is unavailable, LLM calls proceed without caching (just slower). Memory Manager falls back to DB-only mode. Cache miss is the default, not an error.

## Scalability Considerations

| Concern | 100 users | 10K users | 1M users |
|---------|-----------|-----------|----------|
| HTTP serving | Single uvicorn process | Multiple uvicorn workers (--workers N) | Multiple pods behind load balancer |
| Run tracking | In-memory dict in RunManager | Redis-backed run registry | Redis Cluster with run sharding |
| Event streaming | Direct asyncio.Queue per run | Redis Pub/Sub for cross-process events | Redis Streams with consumer groups |
| LLM cache | Single Redis instance | Redis with read replicas | Redis Cluster with hash-based sharding |
| Cost tracking | Per-process in-memory accumulator | Redis atomic counters | OTel metrics pipeline to Prometheus |
| Guardrails | In-process validators | Same (stateless, scales horizontally) | Same (stateless, scales horizontally) |

**Phase 3 target:** 100-user scale. Design interfaces so that upgrading to 10K-user scale in Phase 4 requires only swapping implementations, not changing APIs.

## Sources

- [Building LLM apps with FastAPI — SSE and background tasks](https://dev.to/zachary62/build-an-llm-web-app-in-python-from-scratch-part-4-fastapi-background-tasks-sse-21g4)
- [OpenTelemetry GenAI span conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/)
- [OpenTelemetry GenAI agent span conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/)
- [OTel GenAI metrics conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-metrics/)
- [Redis semantic caching architecture](https://redis.io/blog/building-a-context-enabled-semantic-cache-with-redis/)
- [Guardrails AI API reference](https://www.guardrailsai.com/docs/api_reference_markdown/guards)
- [Portkey: tracking LLM usage across providers](https://portkey.ai/blog/tracking-llm-token-usage-across-providers-teams-and-workloads/)
- [MemGPT/Letta virtual context management](https://research.memgpt.ai/)
- [Mem0 scalable memory architecture](https://arxiv.org/abs/2504.19413)
