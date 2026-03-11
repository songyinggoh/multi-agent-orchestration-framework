# Phase 3.1: Server & API Layer - Deep Research

**Researched:** 2026-03-10
**Domain:** FastAPI server for async agent orchestration with SSE streaming
**Confidence:** HIGH

## Summary

Orchestra needs a production-grade HTTP server that wraps the existing `CompiledGraph` engine, exposing agent workflows as RESTful endpoints with real-time streaming. The research covers six areas: endpoint design patterns from LangServe/LangGraph Platform, SSE vs WebSocket for LLM streaming, async execution lifecycle management, ASGI middleware, health checks, and Pydantic response models.

The core architectural insight is that **FastAPI must be a thin transport layer, not an execution runtime**. Graph runs can outlive HTTP requests (HITL interrupts, long-running multi-agent workflows), so the server needs a `RunManager` that decouples run lifecycle from request lifecycle. The EventBus already emits 18 typed events -- the SSE stream should subscribe to the EventBus and relay events to clients, not poll for results.

**Primary recommendation:** Use FastAPI with native SSE (`fastapi.sse.EventSourceResponse`, available since FastAPI 0.115+) for streaming, a `GraphRegistry` for graph lifecycle management, and `asyncio.Task` for run execution. Do NOT use Celery or background task queues for initial implementation -- the existing async engine maps naturally to ASGI's async model.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.115 | HTTP framework | Native SSE support, async-first, Pydantic v2 integration, auto OpenAPI docs |
| uvicorn | >=0.30 | ASGI server | Standard production server for FastAPI, supports HTTP/1.1 keep-alive for SSE |
| pydantic | >=2.5 | Request/response models | Already in Orchestra's deps, discriminated unions for event types |
| sse-starlette | >=2.1 | SSE fallback/advanced features | Heartbeats, graceful shutdown signals, client disconnect detection; use if FastAPI native SSE lacks needed features |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| slowapi | >=0.1.9 | Rate limiting | Production deployments needing per-client throttling |
| asgi-correlation-id | >=4.3 | Request ID propagation | Correlating HTTP requests with run_ids in logs/traces |
| uvloop | >=0.19 | Event loop optimization | Linux production deployments (not Windows) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SSE (EventSourceResponse) | WebSocket | WebSocket adds bidirectional complexity; SSE is simpler for server-to-client streaming, auto-reconnects, works through HTTP proxies. WebSocket only needed if client sends mid-stream data (not our case -- resume is a separate POST) |
| asyncio.Task for runs | Celery task queue | Celery adds Redis/RabbitMQ dependency and serialization overhead. Orchestra's graph engine is already fully async. Celery only justified at enterprise scale (Phase 4) |
| FastAPI native SSE | sse-starlette | FastAPI 0.115+ has built-in `EventSourceResponse` in `fastapi.sse`. Use sse-starlette only if you need heartbeat keepalives or advanced disconnect handling not yet in FastAPI's native implementation |

**Installation:**
```bash
pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "sse-starlette>=2.1" "slowapi>=0.1.9" "asgi-correlation-id>=4.3"
```

**pyproject.toml optional dependency:**
```toml
[project.optional-dependencies]
server = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sse-starlette>=2.1",
    "slowapi>=0.1.9",
    "asgi-correlation-id>=4.3",
]
```

## Architecture Patterns

### Recommended Project Structure

```
src/orchestra/server/
    __init__.py
    app.py              # FastAPI application factory
    config.py           # Server configuration (Pydantic Settings)
    dependencies.py     # FastAPI dependency injection (get_event_store, get_graph_registry)
    middleware.py        # CORS, request ID, rate limiting setup
    models.py            # Pydantic request/response schemas
    routes/
        __init__.py
        runs.py          # POST /runs, GET /runs/{id}, POST /runs/{id}/resume
        streams.py       # GET /runs/{id}/stream
        graphs.py        # GET /graphs, GET /graphs/{name}
        health.py        # GET /healthz, GET /readyz
    lifecycle.py         # GraphRegistry, RunManager
```

### Pattern 1: Application Factory

**What:** Create the FastAPI app in a factory function for testability.
**When to use:** Always -- enables test clients with different configs.

```python
# src/orchestra/server/app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from orchestra.server.lifecycle import GraphRegistry
from orchestra.server.middleware import setup_middleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    registry = app.state.graph_registry
    await registry.initialize()
    yield
    await registry.shutdown()

def create_app(
    graph_registry: GraphRegistry | None = None,
    debug: bool = False,
) -> FastAPI:
    app = FastAPI(
        title="Orchestra Agent Server",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.graph_registry = graph_registry or GraphRegistry()
    setup_middleware(app)
    # Mount routers
    from orchestra.server.routes import runs, streams, graphs, health
    app.include_router(health.router, tags=["health"])
    app.include_router(graphs.router, prefix="/api/v1", tags=["graphs"])
    app.include_router(runs.router, prefix="/api/v1", tags=["runs"])
    app.include_router(streams.router, prefix="/api/v1", tags=["streams"])
    return app
```

### Pattern 2: Run Lifecycle Decoupled from Request

**What:** Graph executions are managed by a `RunManager` that tracks in-flight runs. An HTTP request creates a run, but the run continues even if the HTTP connection drops (critical for HITL).
**When to use:** All run execution endpoints.

```python
# src/orchestra/server/lifecycle.py
import asyncio
from dataclasses import dataclass, field
from orchestra.core.compiled import CompiledGraph
from orchestra.storage.store import EventBus, EventStore

@dataclass
class ActiveRun:
    run_id: str
    task: asyncio.Task
    event_bus: EventBus
    status: str = "running"  # running | completed | failed | interrupted

class RunManager:
    """Manages in-flight graph executions."""

    def __init__(self, event_store: EventStore | None = None):
        self._runs: dict[str, ActiveRun] = {}
        self._event_store = event_store

    async def start_run(
        self,
        graph: CompiledGraph,
        input_data: dict,
        run_id: str,
    ) -> ActiveRun:
        event_bus = EventBus()
        task = asyncio.create_task(
            graph.run(
                input_data,
                run_id=run_id,
                event_store=self._event_store,
            )
        )
        active = ActiveRun(run_id=run_id, task=task, event_bus=event_bus)
        self._runs[run_id] = active
        return active

    def get_run(self, run_id: str) -> ActiveRun | None:
        return self._runs.get(run_id)
```

### Pattern 3: SSE Event Streaming via EventBus Subscription

**What:** Subscribe to the run's EventBus and yield events as SSE. The async generator bridges Orchestra's internal event model to the HTTP transport.
**When to use:** `/runs/{id}/stream` endpoint.

```python
# src/orchestra/server/routes/streams.py
import asyncio
from collections.abc import AsyncIterable
from fastapi import APIRouter, HTTPException
from fastapi.sse import EventSourceResponse, ServerSentEvent
from orchestra.storage.events import WorkflowEvent

router = APIRouter()

@router.get("/runs/{run_id}/stream", response_class=EventSourceResponse)
async def stream_run(run_id: str) -> AsyncIterable[ServerSentEvent]:
    """Stream run events via SSE."""
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(404, detail=f"Run {run_id} not found")

    queue: asyncio.Queue[WorkflowEvent | None] = asyncio.Queue()

    async def _relay(event: WorkflowEvent) -> None:
        await queue.put(event)

    handle = run.event_bus.subscribe(_relay)
    try:
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=30.0)
            if event is None:
                break
            yield ServerSentEvent(
                data=event.model_dump_json(),
                event=event.event_type.value,
                id=str(event.sequence),
            )
            if event.event_type.value in (
                "execution.completed", "execution.failed"
            ):
                break
    except asyncio.TimeoutError:
        # Send keepalive comment
        yield ServerSentEvent(comment="keepalive")
    finally:
        run.event_bus.unsubscribe(handle)
```

### Pattern 4: GraphRegistry for Lifecycle Management

**What:** A registry that holds compiled graphs, loaded at startup or registered dynamically. Graphs are identified by name/version.
**When to use:** Server startup; dynamic graph registration endpoints.

```python
# src/orchestra/server/lifecycle.py
from orchestra.core.graph import WorkflowGraph
from orchestra.core.compiled import CompiledGraph

class GraphRegistry:
    """Manages compiled graph definitions."""

    def __init__(self):
        self._graphs: dict[str, CompiledGraph] = {}

    def register(self, name: str, graph: WorkflowGraph) -> CompiledGraph:
        compiled = graph.compile()
        self._graphs[name] = compiled
        return compiled

    def get(self, name: str) -> CompiledGraph | None:
        return self._graphs.get(name)

    def list_graphs(self) -> list[str]:
        return list(self._graphs.keys())

    async def initialize(self) -> None:
        """Load graphs from configured sources at startup."""
        pass  # Auto-discovery from entry points or config

    async def shutdown(self) -> None:
        """Cleanup on server shutdown."""
        pass
```

### Anti-Patterns to Avoid

- **Coupling run lifecycle to HTTP request lifecycle:** If a client disconnects during a streaming response, the run must NOT be cancelled. Runs are first-class objects that persist beyond any single HTTP connection. Use `asyncio.Task` tracked in RunManager, not `BackgroundTasks`.

- **Blocking the event loop with synchronous operations:** All graph execution is async. Never use `asyncio.run()` inside a request handler. Never use `run_in_executor()` for the graph engine.

- **Making FastAPI the graph runtime:** FastAPI routes should be thin -- validate input, delegate to CompiledGraph, serialize output. Business logic stays in `core/`.

- **Using WebSocket for one-way streaming:** SSE is simpler, auto-reconnects, works through HTTP/1.1 proxies and CDNs. WebSocket is only warranted for bidirectional real-time communication (not needed here).

- **Polling for run status:** Use EventBus subscription + SSE instead of `GET /runs/{id}/status` polling loops. Polling wastes resources and adds latency.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSE protocol compliance | Custom `text/event-stream` formatting | `fastapi.sse.EventSourceResponse` or `sse-starlette` | SSE spec has edge cases (multiline data, retry fields, BOM handling) |
| Rate limiting | Custom middleware counter | `slowapi` with Redis backend | Distributed counting, sliding windows, per-route limits |
| Request ID propagation | Manual header parsing | `asgi-correlation-id` | Integrates with structlog, handles generation + propagation |
| CORS handling | Manual header injection | `fastapi.middleware.cors.CORSMiddleware` | Preflight handling, credential support, origin patterns |
| API key auth | Custom header parsing | `fastapi.security.APIKeyHeader` | OpenAPI integration, automatic 403 on missing key |
| OpenAPI schema | Manual schema writing | FastAPI auto-generation from Pydantic models | Automatic, always in sync with code |

**Key insight:** The entire middleware and auth stack is solved by FastAPI's ecosystem. Zero custom middleware needed for initial production.

## Endpoint Design (Industry Standard)

Based on LangServe, LangGraph Platform, and CrewAI patterns, the standard endpoint set for agent orchestration is:

### Core Endpoints

| Method | Path | Purpose | Response |
|--------|------|---------|----------|
| POST | `/api/v1/runs` | Start a new graph execution | `RunResponse` (201) |
| GET | `/api/v1/runs/{run_id}` | Get run status and result | `RunResponse` (200) |
| POST | `/api/v1/runs/{run_id}/resume` | Resume HITL-interrupted run | `RunResponse` (200) |
| GET | `/api/v1/runs/{run_id}/stream` | Stream run events via SSE | SSE stream |
| GET | `/api/v1/runs/{run_id}/events` | Get historical events for a run | `list[EventResponse]` |
| GET | `/api/v1/runs` | List recent runs | `list[RunSummary]` |

### Graph Management

| Method | Path | Purpose | Response |
|--------|------|---------|----------|
| GET | `/api/v1/graphs` | List registered graphs | `list[GraphInfo]` |
| GET | `/api/v1/graphs/{name}` | Get graph details + Mermaid diagram | `GraphDetail` |
| GET | `/api/v1/graphs/{name}/schema` | Get graph input/output schema | JSON Schema |

### Health & Operations

| Method | Path | Purpose | Response |
|--------|------|---------|----------|
| GET | `/healthz` | Liveness probe (is process alive?) | `{"status": "ok"}` (200) |
| GET | `/readyz` | Readiness probe (can accept traffic?) | `{"status": "ready"}` (200) or 503 |

### Design Decisions

- **`/api/v1/` prefix:** Enables API versioning from day one. Health endpoints are at root (Kubernetes convention).
- **POST for run creation, GET for streaming:** LangGraph Platform uses `POST /runs/stream` to combine creation and streaming. We separate them for better REST semantics and reconnectability -- a client can disconnect from the SSE stream and reconnect to the same `run_id` without restarting the run.
- **Resume as POST, not PATCH:** Resume involves submitting state modifications (e.g., `approved=true`), which is a command, not a partial update. POST is semantically correct.

## Pydantic Response Models

### Request Models

```python
from pydantic import BaseModel, Field
from typing import Any

class RunCreate(BaseModel):
    """Request to start a new graph execution."""
    graph_name: str = Field(..., description="Name of the registered graph")
    input: dict[str, Any] = Field(default_factory=dict, description="Initial state / input data")
    config: RunConfig | None = None

class RunConfig(BaseModel):
    """Optional run configuration."""
    max_turns: int = Field(50, ge=1, le=1000)
    provider: str | None = Field(None, description="Override LLM provider name")
    persist: bool = True
    stream: bool = Field(False, description="If true, response streams SSE instead of waiting")

class ResumeRequest(BaseModel):
    """Request to resume an interrupted run."""
    state_updates: dict[str, Any] = Field(
        default_factory=dict,
        description="State modifications (e.g., {'approved': true})",
    )
```

### Response Models

```python
from datetime import datetime
from enum import Enum

class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"

class RunResponse(BaseModel):
    """Response for a run."""
    run_id: str
    graph_name: str
    status: RunStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class StreamEvent(BaseModel):
    """SSE event payload -- serialized from WorkflowEvent."""
    event_type: str
    sequence: int
    timestamp: datetime
    data: dict[str, Any]

class GraphInfo(BaseModel):
    """Summary of a registered graph."""
    name: str
    entry_point: str
    node_count: int
    has_interrupts: bool

class GraphDetail(GraphInfo):
    """Full graph details including visualization."""
    nodes: list[str]
    edges: list[dict[str, str]]
    mermaid: str  # From CompiledGraph.to_mermaid()

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: str | None = None
    run_id: str | None = None
```

## SSE vs WebSocket Analysis

| Factor | SSE | WebSocket |
|--------|-----|-----------|
| Direction | Server-to-client only | Bidirectional |
| Protocol | HTTP/1.1 (text/event-stream) | Upgrade to ws:// |
| Auto-reconnect | Built into browser EventSource API | Must implement manually |
| Proxy/CDN support | Works through standard HTTP infrastructure | Requires WebSocket-aware proxies |
| Backpressure | TCP flow control (HTTP) | Must implement application-level |
| Complexity | Low -- async generator yields data | High -- connection management, ping/pong |
| Use case fit | Token streaming, event feeds | Chat UIs needing client-to-server mid-stream |

**Verdict: Use SSE.** Orchestra's streaming is unidirectional (server sends events to client). Client actions (resume, cancel) use separate HTTP endpoints. SSE is simpler, more reliable through infrastructure, and matches the LangGraph Platform pattern.

**For the rare case where bidirectional streaming is needed** (e.g., interactive chat where user sends messages mid-stream), add a WebSocket endpoint later as an opt-in upgrade path. Do not make it the default.

## Async Execution Strategy

### The Problem
`CompiledGraph.run()` is fully async and can take seconds to minutes. FastAPI request handlers must not block, and long-running runs should survive client disconnects.

### The Solution: asyncio.Task + EventBus

```
Client                  FastAPI                    RunManager                CompiledGraph
  |                       |                           |                          |
  |-- POST /runs -------->|                           |                          |
  |                       |-- start_run() ----------->|                          |
  |                       |                           |-- asyncio.create_task -->|
  |<-- 201 {run_id} ------|                           |     graph.run()          |
  |                       |                           |                          |
  |-- GET /runs/{id}/stream -->|                      |                          |
  |                       |-- subscribe(event_bus) -->|                          |
  |<-- SSE: node.started -|<-- event ------------------|<-- emit() --------------|
  |<-- SSE: node.completed|<-- event ------------------|<-- emit() --------------|
  |<-- SSE: exec.completed|<-- event ------------------|                          |
  |                       |-- unsubscribe() -------->|                          |
```

Key points:
1. `POST /runs` returns immediately with 201 + `run_id`. The graph runs in a background `asyncio.Task`.
2. `GET /runs/{id}/stream` subscribes to the run's EventBus and relays events as SSE.
3. If the client disconnects from the SSE stream, the run continues. The client can reconnect.
4. HITL interrupts emit `interrupt.requested` via SSE, then the run awaits. Client sends `POST /runs/{id}/resume`.

### Why NOT Celery/Task Queues

- Orchestra's engine is already async. Wrapping it in Celery would require serializing state to Redis/RabbitMQ, losing the in-process EventBus subscription model.
- Celery workers run in separate processes, making SSE streaming impossible without an additional pub/sub layer.
- For Phase 3 (single-server deployment), asyncio.Task is sufficient. Celery/distributed queues belong in Phase 4 (Enterprise & Scale) when multi-node deployments are needed.

## ASGI Middleware Chain

### Recommended Order (outermost to innermost)

```python
# src/orchestra/server/middleware.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from asgi_correlation_id import CorrelationIdMiddleware

def setup_middleware(app: FastAPI) -> None:
    # 1. CORS -- must be outermost
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    # 2. Request ID propagation
    app.add_middleware(
        CorrelationIdMiddleware,
        header_name="X-Request-ID",
    )

    # 3. Rate limiting (via slowapi -- added per-route, not as global middleware)
    # slowapi uses route decorators: @limiter.limit("10/minute")
```

### Middleware Execution Order Note
ASGI middleware executes in reverse registration order (last registered = first to execute on request). Register CORS first so it wraps everything.

## Health Check Patterns

```python
# src/orchestra/server/routes/health.py
from fastapi import APIRouter, Response

router = APIRouter()

@router.get("/healthz")
async def liveness():
    """Liveness probe. Lightweight -- just confirms process is alive."""
    return {"status": "ok"}

@router.get("/readyz")
async def readiness(response: Response):
    """Readiness probe. Checks critical dependencies."""
    checks = {}

    # Check event store connectivity
    try:
        store = get_event_store()
        if store:
            await store.list_runs(limit=1)
            checks["event_store"] = "ok"
    except Exception as e:
        checks["event_store"] = f"error: {e}"
        response.status_code = 503

    # Check graph registry has at least one graph
    registry = get_graph_registry()
    graph_count = len(registry.list_graphs())
    checks["graphs_loaded"] = graph_count
    if graph_count == 0:
        checks["graphs"] = "warning: no graphs registered"

    return {"status": "ready" if response.status_code != 503 else "not_ready", "checks": checks}
```

### Kubernetes Probe Configuration
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /readyz
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 5
```

## Common Pitfalls

### Pitfall 1: Blocking the Event Loop with Synchronous Graph Code
**What goes wrong:** A synchronous function node blocks the entire ASGI server.
**Why it happens:** Not all user-defined node functions are `async`.
**How to avoid:** Wrap synchronous functions in `asyncio.to_thread()` at the node execution layer. The existing `_execute_node` in compiled.py already handles async -- verify sync functions are properly wrapped.
**Warning signs:** Server stops responding to health checks during graph execution.

### Pitfall 2: SSE Connection Held Open After Run Completes
**What goes wrong:** The SSE async generator never yields a termination signal, keeping the HTTP connection open indefinitely.
**Why it happens:** Missing sentinel event or timeout.
**How to avoid:** Always yield a final SSE event with `event: done` when `ExecutionCompleted` or `ErrorOccurred` is emitted. Implement a 30-second keepalive timeout that sends SSE comments.
**Warning signs:** Connection count grows monotonically in production metrics.

### Pitfall 3: Multiple SSE Subscribers Getting Duplicate Events
**What goes wrong:** Two clients streaming the same run_id both subscribe to the same EventBus, causing each event to be processed twice (once per subscriber callback).
**Why it happens:** EventBus broadcasts to all subscribers.
**How to avoid:** This is correct behavior -- each subscriber gets its own queue. The issue arises only if subscribers have side effects. For SSE, each client gets its own async generator with its own queue. No shared mutable state.

### Pitfall 4: CORS Blocking SSE Connections
**What goes wrong:** Browser EventSource fails with CORS errors.
**Why it happens:** SSE uses GET requests, which are subject to CORS. The `EventSource` API does not support custom headers.
**How to avoid:** Ensure CORS middleware allows the origin. For authenticated SSE, pass tokens as query parameters (not headers) since EventSource does not support custom headers.
**Warning signs:** Works in Postman/curl but fails in browser.

### Pitfall 5: Run State Lost on Server Restart
**What goes wrong:** In-memory RunManager loses all active run references.
**Why it happens:** asyncio.Tasks are not persisted.
**How to avoid:** Runs are persisted to EventStore. On server restart, historical runs are queryable from the store. Active runs that were interrupted by restart can be resumed via `POST /runs/{id}/resume` (checkpoints are in the EventStore). The RunManager is for in-flight tracking only.
**Warning signs:** Run status shows "running" in database but no asyncio.Task exists.

### Pitfall 6: Request Timeouts Killing Long Runs
**What goes wrong:** Uvicorn or a reverse proxy (nginx) kills the SSE connection after 60 seconds.
**Why it happens:** Default HTTP timeouts.
**How to avoid:** Configure uvicorn with `--timeout-keep-alive 120`. For nginx: `proxy_read_timeout 3600;`. SSE keepalive comments (every 15-30s) prevent idle timeouts.
**Warning signs:** SSE streams disconnect at exactly 60 seconds.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LangServe `/invoke`, `/stream` | LangGraph Platform with `/threads/{id}/runs/stream` | 2025 | Thread-based state management, resumable streams |
| `sse-starlette` required | FastAPI native `fastapi.sse.EventSourceResponse` | FastAPI 0.115 (2025) | One fewer dependency; sse-starlette still useful for advanced features |
| WebSocket for LLM streaming | SSE as industry standard | 2024-2025 | OpenAI, Anthropic, Google all use SSE for streaming APIs |
| Polling for run status | EventBus subscription + SSE streaming | N/A (architecture choice) | Real-time updates, lower latency, lower server load |
| Synchronous task queues (Celery) | asyncio.Task for single-server | 2024-2025 | Simpler deployment, preserves in-process event model |

**Deprecated/outdated:**
- **LangServe:** LangChain officially recommends LangGraph Platform over LangServe for new projects. LangServe's `/invoke`/`/stream` pattern is being superseded by thread+run model.
- **Flask for AI serving:** Flask's WSGI model is fundamentally incompatible with async streaming. All modern agent frameworks use ASGI (FastAPI/Starlette).

## Integration with Orchestra's Existing Architecture

### EventBus as Streaming Backbone
Orchestra already has a fully functional EventBus with 18 typed events and subscriber callbacks. The SSE streaming endpoint simply adds another subscriber. No changes to the event system are needed.

### CompiledGraph.run() Signature Compatibility
The existing `run()` method already accepts `run_id`, `event_store`, `input`, and `provider` -- exactly the parameters the server needs to pass. No refactoring required.

### EventStore for Run History
The `EventStore.list_runs()`, `get_events()`, and `get_latest_checkpoint()` methods provide everything needed for the `GET /runs` and `GET /runs/{id}` endpoints.

### CLI Integration
The existing CLI (`typer`-based) can get a `serve` command:
```python
@app.command()
def serve(
    host: str = "0.0.0.0",
    port: int = 8000,
    reload: bool = False,
):
    """Start the Orchestra API server."""
    import uvicorn
    uvicorn.run("orchestra.server.app:create_app", host=host, port=port, reload=reload, factory=True)
```

## Open Questions

1. **Authentication strategy**
   - What we know: FastAPI supports API key headers, OAuth2, and JWT natively. SlowAPI can rate-limit by auth identity.
   - What's unclear: Should Phase 3 implement auth, or defer to Phase 4 (Enterprise & Scale) which has "Agent IAM"?
   - Recommendation: Add optional API key header support in Phase 3 (simple `X-API-Key` check). Full IAM in Phase 4.

2. **Multi-graph concurrency limits**
   - What we know: asyncio.Task allows unbounded concurrency.
   - What's unclear: Should there be a max concurrent runs limit per server?
   - Recommendation: Add a configurable `max_concurrent_runs` in server config (default 100). Return 429 when exceeded.

3. **SSE reconnection and event replay**
   - What we know: LangGraph Platform supports resumable streams. SSE supports `Last-Event-ID` header for reconnection.
   - What's unclear: Should Orchestra replay missed events on reconnect?
   - Recommendation: Support `Last-Event-ID` using the event sequence number. On reconnect, fetch missed events from EventStore via `get_events(run_id, after_sequence=last_event_id)`.

## Sources

### Primary (HIGH confidence)
- FastAPI official docs -- SSE tutorial (`fastapi.tiangolo.com/tutorial/server-sent-events/`)
- FastAPI official docs -- middleware (`fastapi.tiangolo.com/advanced/middleware/`)
- Kubernetes docs -- liveness/readiness probes (`kubernetes.io/docs`)
- Pydantic v2 docs -- discriminated unions (`docs.pydantic.dev/latest/concepts/unions/`)
- LangGraph Platform API Reference (`langchain-ai.github.io/langgraph/cloud/reference/api/api_ref.html`)

### Secondary (MEDIUM confidence)
- sse-starlette GitHub (`github.com/sysid/sse-starlette`) -- production SSE features
- asgi-correlation-id PyPI (`pypi.org/project/asgi-correlation-id/`) -- request ID propagation
- slowapi GitHub (`github.com/laurentS/slowapi`) -- rate limiting
- LangServe GitHub (`github.com/langchain-ai/langserve`) -- endpoint patterns (note: deprecated in favor of LangGraph Platform)
- CrewAI community patterns -- FastAPI wrapping for agent crews

### Tertiary (LOW confidence)
- Various Medium/DEV.to articles on FastAPI+SSE streaming for LLM agents (consistent patterns across multiple sources, but not official documentation)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - FastAPI + SSE is the undisputed standard for Python agent serving in 2025-2026
- Architecture (run lifecycle decoupling): HIGH - consistent across LangGraph Platform, CrewAI, and community patterns
- SSE vs WebSocket: HIGH - all major LLM API providers (OpenAI, Anthropic, Google) use SSE
- Middleware chain: HIGH - FastAPI's built-in middleware ecosystem is well-documented
- Pydantic models: HIGH - already used extensively in Orchestra's codebase
- Health checks: HIGH - Kubernetes patterns are standardized
- Pitfalls: MEDIUM - derived from multiple community sources and architectural reasoning

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (FastAPI ecosystem is stable; SSE patterns are settled)
