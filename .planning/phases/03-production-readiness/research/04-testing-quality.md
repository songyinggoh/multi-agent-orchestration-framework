# Phase 3: Testing & Quality - Research

**Researched:** 2026-03-10
**Domain:** Testing infrastructure for async Python multi-agent orchestration
**Confidence:** HIGH (well-established ecosystem, verified across multiple sources)

## Summary

Orchestra's testing needs span nine distinct domains: load testing, chaos/fault injection, deterministic replay, contract/protocol conformance, Docker-based integration infrastructure, snapshot testing, FastAPI endpoint testing, concurrency verification, and property-based testing. The Python ecosystem has mature, well-documented solutions for every one of these.

The existing test infrastructure (244 pytest tests, `ScriptedLLM`, `ReplayProvider`, `pytest-asyncio` with `asyncio_mode = "auto"`) provides a strong foundation. The primary gaps are: (1) no load/stress testing, (2) no fault injection framework, (3) no snapshot/golden-file regression suite, (4) no containerized integration tests for Postgres/Redis, and (5) no property-based testing for graph topologies.

**Primary recommendation:** Use Locust for load testing (Python-native, async-aware), custom fault-injection decorators over Toxiproxy (simpler for LLM provider testing), Syrupy for snapshot testing, testcontainers-python for Docker integration tests, and Hypothesis for property-based graph topology generation.

## Standard Stack

### Core Testing (already installed)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| pytest | >=8.0 | Test runner | Already in dev deps |
| pytest-asyncio | >=0.23 | Async test support | Already in dev deps |
| pytest-cov | >=4.1 | Coverage reporting | Already in dev deps |

### New Testing Libraries
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| locust | >=2.31 | Load/stress testing | Python-native, async support, built-in web UI, SSE testing via `stream=True` |
| hypothesis | >=6.120 | Property-based testing | De facto standard for Python PBT, 5% of Python devs use it |
| syrupy | >=4.8 | Snapshot testing | Idiomatic pytest integration (`assert x == snapshot`), active maintenance |
| testcontainers | >=4.14 | Docker containers in tests | Standard for Python integration tests, modules for postgres/redis |
| httpx | >=0.26 | Async HTTP client for FastAPI tests | Already a core dependency, used with `ASGITransport` |
| pytest-repeat | >=0.9 | Repeat tests for flaky detection | Useful for race condition hunting with `--count 100` |
| asgi-lifespan | >=2.1 | Lifespan event handling in tests | Required when FastAPI app uses lifespan events |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Locust | k6 | k6 is faster (Go-based) but requires JavaScript; Locust keeps everything Python |
| Locust | vegeta | vegeta is CLI-only, no Python integration, better for simple HTTP hammering |
| Syrupy | pytest-snapshot | pytest-snapshot is less maintained; Syrupy has better pytest integration |
| Syrupy | inline-snapshot | inline-snapshot puts snapshots in test code; worse for large event streams |
| testcontainers | docker-compose | docker-compose requires external process management; testcontainers is programmatic |
| Toxiproxy | Custom decorators | Toxiproxy needs a proxy process; custom decorators are lighter for LLM testing |

**Installation:**
```bash
pip install locust hypothesis syrupy "testcontainers[postgres,redis]" pytest-repeat asgi-lifespan
```

Or add to `pyproject.toml` under `[project.optional-dependencies]`:
```toml
test-advanced = [
    "locust>=2.31",
    "hypothesis>=6.120",
    "syrupy>=4.8",
    "testcontainers[postgres,redis]>=4.14",
    "pytest-repeat>=0.9",
    "asgi-lifespan>=2.1",
]
```

## Architecture Patterns

### Recommended Test Directory Structure
```
tests/
  conftest.py                    # Shared fixtures (ScriptedLLM, event helpers)
  unit/                          # Fast, no I/O (existing 244 tests)
    test_core.py
    test_events.py
    ...
  integration/                   # Docker-dependent tests (testcontainers)
    conftest.py                  # Container fixtures (postgres, redis)
    test_postgres_integration.py
    test_redis_integration.py
    test_fastapi_endpoints.py
  load/                          # Locust load test scripts
    locustfile.py                # Main load test definitions
    conftest.py                  # Locust environment config
  property/                      # Hypothesis property-based tests
    test_graph_topologies.py
    test_state_reducers.py
  snapshots/                     # Syrupy golden files (auto-generated)
    __snapshots__/
  chaos/                         # Fault injection tests
    test_provider_faults.py
    test_storage_faults.py
    fault_injectors.py           # Reusable fault injection decorators
```

### Pattern 1: FastAPI Async Endpoint Testing
**What:** Test FastAPI endpoints using httpx.AsyncClient with ASGITransport
**When to use:** All FastAPI endpoint tests (Wave 1 of Phase 3)

```python
# tests/integration/conftest.py
import pytest
from httpx import ASGITransport, AsyncClient
from asgi_lifespan import LifespanManager

from orchestra.server.app import create_app

@pytest.fixture
async def app():
    """Create test application with lifespan events."""
    app = create_app()
    async with LifespanManager(app) as manager:
        yield manager.app

@pytest.fixture
async def client(app):
    """Async HTTP client for testing FastAPI endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

```python
# tests/integration/test_fastapi_endpoints.py
async def test_create_run(client):
    response = await client.post("/runs", json={
        "workflow": "research",
        "input": {"query": "test"},
    })
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data

async def test_stream_run_sse(client):
    """Test SSE streaming endpoint."""
    async with client.stream(
        "GET", "/runs/test-id/stream",
        headers={"Accept": "text/event-stream"},
    ) as response:
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(line[6:])
        assert len(events) > 0
```

### Pattern 2: Fault Injection Decorators for LLM Providers
**What:** Custom decorators that wrap LLM providers to inject failures deterministically
**When to use:** Chaos testing of provider resilience without external proxy processes

```python
# tests/chaos/fault_injectors.py
from __future__ import annotations
import asyncio
import random
from functools import wraps
from typing import Any

from orchestra.core.types import LLMResponse, Message


class FaultInjector:
    """Wraps an LLM provider to inject configurable faults."""

    def __init__(
        self,
        provider: Any,
        *,
        timeout_rate: float = 0.0,       # Probability of timeout
        error_rate: float = 0.0,         # Probability of API error
        malformed_rate: float = 0.0,     # Probability of malformed response
        latency_ms: tuple[int, int] = (0, 0),  # (min, max) added latency
    ):
        self._provider = provider
        self._timeout_rate = timeout_rate
        self._error_rate = error_rate
        self._malformed_rate = malformed_rate
        self._latency_ms = latency_ms
        self._fault_log: list[dict] = []

    async def complete(self, messages: list[Message], **kwargs) -> LLMResponse:
        # Inject latency
        if self._latency_ms[1] > 0:
            delay = random.randint(*self._latency_ms) / 1000
            await asyncio.sleep(delay)

        # Inject timeout
        if random.random() < self._timeout_rate:
            self._fault_log.append({"type": "timeout", "call": len(self._fault_log)})
            raise TimeoutError("Injected timeout")

        # Inject API error
        if random.random() < self._error_rate:
            self._fault_log.append({"type": "error", "call": len(self._fault_log)})
            raise ConnectionError("Injected provider error")

        # Inject malformed response
        if random.random() < self._malformed_rate:
            self._fault_log.append({"type": "malformed", "call": len(self._fault_log)})
            return LLMResponse(content="")  # Empty/malformed

        return await self._provider.complete(messages, **kwargs)

    @property
    def fault_log(self) -> list[dict]:
        return self._fault_log
```

```python
# tests/chaos/test_provider_faults.py
from orchestra.testing import ScriptedLLM
from tests.chaos.fault_injectors import FaultInjector

async def test_runner_retries_on_timeout():
    """Verify the runner retries when provider times out."""
    base = ScriptedLLM(["success response"] * 3)
    faulty = FaultInjector(base, timeout_rate=0.5)
    # Run workflow with faulty provider, assert it eventually succeeds
    # or fails gracefully after max retries

async def test_runner_handles_rate_limit():
    """Simulate rate limiting with 429-like errors."""
    base = ScriptedLLM(["ok"])
    faulty = FaultInjector(base, error_rate=1.0)
    # Assert proper error propagation
```

### Pattern 3: Deterministic Replay / Golden File Testing
**What:** Record LLM interactions during a "golden run", replay them for regression testing
**When to use:** Regression testing of agent workflows, ensuring output stability

```python
# Orchestra already has ReplayProvider in src/orchestra/providers/replay.py
# and event serialization in src/orchestra/storage/serialization.py
# These can be composed for golden-file testing:

import json
from pathlib import Path
from orchestra.providers.replay import ReplayProvider
from orchestra.storage.serialization import events_to_jsonl, jsonl_to_events

GOLDEN_DIR = Path("tests/snapshots/golden_runs")

def record_golden_run(events: list, name: str):
    """Save events from a run as a golden file."""
    path = GOLDEN_DIR / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(events_to_jsonl(events))

def load_golden_run(name: str) -> list:
    """Load events from a golden file."""
    path = GOLDEN_DIR / f"{name}.jsonl"
    return jsonl_to_events(path.read_text())

async def test_workflow_matches_golden_run():
    """Replay a recorded run and verify output matches."""
    golden_events = load_golden_run("research_workflow_v1")
    replay = ReplayProvider(golden_events)
    # Run workflow with replay provider
    # Compare output events against golden file
```

### Pattern 4: Snapshot Testing with Syrupy
**What:** Automatic snapshot comparison for event streams and API responses
**When to use:** Regression testing of serialized event output, API response shapes

```python
# tests/unit/test_event_snapshots.py
def test_execution_started_serialization(snapshot):
    from orchestra.storage.events import ExecutionStarted
    from orchestra.storage.serialization import event_to_dict

    event = ExecutionStarted(
        run_id="test-run",
        workflow_name="research",
        initial_state={"query": "test"},
        entry_point="start",
    )
    result = event_to_dict(event)
    # Remove timestamp for deterministic comparison
    result.pop("timestamp", None)
    assert result == snapshot
```

### Pattern 5: Protocol Conformance Suites
**What:** Parameterized test classes that verify any implementation satisfies a protocol
**When to use:** Verifying EventStore, LLMProvider implementations

```python
# tests/conformance/test_eventstore_conformance.py
import pytest
from abc import ABC, abstractmethod

class EventStoreConformanceSuite(ABC):
    """Base conformance suite for EventStore protocol.

    Subclass and implement `create_store()` to test any implementation.
    """

    @abstractmethod
    async def create_store(self):
        """Return a fresh EventStore instance."""
        ...

    async def test_append_and_retrieve(self):
        store = await self.create_store()
        event = make_execution_started()
        await store.append(event)
        events = await store.get_events("run-1")
        assert len(events) == 1

    async def test_get_events_empty_run(self):
        store = await self.create_store()
        events = await store.get_events("nonexistent")
        assert events == []

    async def test_event_ordering(self):
        store = await self.create_store()
        e1 = make_execution_started(sequence=0)
        e2 = make_node_started(sequence=1)
        await store.append(e1)
        await store.append(e2)
        events = await store.get_events("run-1")
        assert events[0].sequence < events[1].sequence


class TestInMemoryConformance(EventStoreConformanceSuite):
    async def create_store(self):
        from orchestra.storage.store import InMemoryEventStore
        return InMemoryEventStore()


class TestSQLiteConformance(EventStoreConformanceSuite):
    async def create_store(self):
        from orchestra.storage.sqlite import SQLiteEventStore
        store = SQLiteEventStore(":memory:")
        await store.initialize()
        return store
```

### Pattern 6: testcontainers for Docker Integration
**What:** Programmatic Docker containers for integration tests
**When to use:** Testing against real Postgres, Redis instances

```python
# tests/integration/conftest.py
import pytest
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

@pytest.fixture(scope="module")
def postgres_container():
    """Start a PostgreSQL container for the test module."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg

@pytest.fixture
async def postgres_store(postgres_container):
    """Create a PostgresEventStore connected to the test container."""
    from orchestra.storage.postgres import PostgresEventStore
    url = postgres_container.get_connection_url()
    # Convert to asyncpg format
    url = url.replace("postgresql+psycopg2://", "postgresql://")
    store = PostgresEventStore(url)
    await store.initialize()
    yield store
    await store.close()

@pytest.fixture(scope="module")
def redis_container():
    """Start a Redis container for the test module."""
    with RedisContainer("redis:7-alpine") as redis:
        yield redis
```

### Pattern 7: Property-Based Testing with Hypothesis
**What:** Generate random graph topologies and verify invariants
**When to use:** Testing graph engine robustness against edge cases

```python
# tests/property/test_graph_topologies.py
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Strategy for generating valid DAG node names
node_names = st.text(
    alphabet=st.characters(whitelist_categories=("L",)),
    min_size=1, max_size=10,
)

@st.composite
def dag_topology(draw):
    """Generate a random DAG as a dict of node -> list[successor]."""
    n_nodes = draw(st.integers(min_value=2, max_value=8))
    names = draw(st.lists(node_names, min_size=n_nodes, max_size=n_nodes, unique=True))

    edges = {}
    for i, name in enumerate(names):
        # Only allow edges to nodes with higher indices (guarantees DAG)
        possible_targets = names[i + 1:]
        if possible_targets:
            targets = draw(st.lists(
                st.sampled_from(possible_targets),
                max_size=min(3, len(possible_targets)),
                unique=True,
            ))
            edges[name] = targets
        else:
            edges[name] = []

    return names, edges

@given(topology=dag_topology())
@settings(max_examples=100)
def test_dag_has_no_cycles(topology):
    """Every generated topology should be cycle-free."""
    names, edges = topology
    # Verify topological sort is possible (no cycles)
    visited = set()
    temp = set()

    def dfs(node):
        if node in temp:
            raise ValueError("Cycle detected")
        if node in visited:
            return
        temp.add(node)
        for succ in edges.get(node, []):
            dfs(succ)
        temp.remove(node)
        visited.add(node)

    for name in names:
        dfs(name)

@given(topology=dag_topology())
@settings(max_examples=50)
async def test_graph_compiles_any_valid_dag(topology):
    """Any valid DAG should compile without errors."""
    names, edges = topology
    from orchestra.core.graph import WorkflowGraph
    graph = WorkflowGraph(name="generated")
    # Add nodes and edges, verify compilation succeeds
```

### Pattern 8: Concurrency Testing
**What:** Verify thread safety of parallel graph execution
**When to use:** Testing parallel node execution, shared state access

```python
# tests/integration/test_concurrency.py
import asyncio

async def test_parallel_node_execution_no_race():
    """Run multiple graph instances concurrently, verify no state corruption."""
    from orchestra.core.graph import WorkflowGraph
    from orchestra.core.runner import run
    from orchestra.testing import ScriptedLLM

    results = []

    async def run_one(index: int):
        llm = ScriptedLLM([f"result-{index}"])
        # Build and run a simple graph
        graph = WorkflowGraph(name=f"test-{index}")
        # ... configure graph ...
        result = await run(graph, {"input": f"query-{index}"}, llm=llm)
        results.append(result)

    # Run 20 graphs concurrently
    await asyncio.gather(*[run_one(i) for i in range(20)])
    assert len(results) == 20
    # Verify no cross-contamination
    for i, r in enumerate(results):
        assert f"result-{i}" in str(r)

async def test_eventstore_concurrent_writes():
    """Verify EventStore handles concurrent appends correctly."""
    from orchestra.storage.store import InMemoryEventStore
    store = InMemoryEventStore()

    async def write_events(run_id: str, count: int):
        for i in range(count):
            event = make_execution_started(run_id=run_id, sequence=i)
            await store.append(event)

    await asyncio.gather(*[
        write_events(f"run-{i}", 50) for i in range(10)
    ])

    # Verify all events persisted correctly
    for i in range(10):
        events = await store.get_events(f"run-{i}")
        assert len(events) == 50
```

### Pattern 9: Load Testing SSE Streaming Endpoints
**What:** Locust script for load testing FastAPI endpoints including SSE streams
**When to use:** Validating API performance before production deployment

```python
# tests/load/locustfile.py
from locust import HttpUser, task, between

class OrchestraUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def create_run(self):
        """Submit a workflow run."""
        self.client.post("/runs", json={
            "workflow": "research",
            "input": {"query": "test query"},
        })

    @task(1)
    def stream_run(self):
        """Test SSE streaming endpoint."""
        with self.client.get(
            "/runs/demo/stream",
            headers={
                "Accept": "text/event-stream",
                "Cache-Control": "no-cache",
            },
            stream=True,
            catch_response=True,
        ) as response:
            event_count = 0
            for line in response.iter_lines():
                if line and line.startswith(b"data: "):
                    event_count += 1
                    if event_count >= 10:
                        break
            if event_count > 0:
                response.success()
            else:
                response.failure("No SSE events received")

    @task(2)
    def get_run_status(self):
        """Check run status."""
        self.client.get("/runs/demo")
```

### Anti-Patterns to Avoid
- **Mocking too much in integration tests:** Use real containers (testcontainers) instead of mocking Postgres/Redis in integration tests. Mocks hide real issues like connection pooling, serialization, and SQL dialect differences.
- **Non-deterministic snapshot timestamps:** Always strip or freeze timestamps before snapshot comparison. Use `freezegun` or filter fields in serialization.
- **Shared mutable state in async tests:** Each test must create its own `ScriptedLLM`, `InMemoryEventStore`, etc. Never share mutable fixtures across async tests without locks.
- **Testing streaming with regular HTTP calls:** SSE endpoints require `stream=True` and iterating lines. A regular `client.get()` will buffer the entire response or timeout.
- **Ignoring event loop policy:** On Windows, use `WindowsSelectorEventLoopPolicy` for compatibility. Set via `pytest.ini` or `conftest.py`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Load testing framework | Custom HTTP hammering scripts | Locust | Distributed execution, web UI, statistics, SSE support |
| Snapshot comparison | Manual JSON diff assertions | Syrupy | Handles snapshot creation, update workflow, CI-safe assertions |
| Container management | Shell scripts starting Docker | testcontainers-python | Programmatic lifecycle, port mapping, health checks, cleanup |
| Random test data | Hand-written edge cases | Hypothesis | Finds edge cases humans miss, shrinks to minimal failing example |
| Async test orchestration | Custom event loop management | pytest-asyncio (auto mode) | Already configured in project, handles loop creation/teardown |
| Flaky test detection | Manual re-runs | pytest-repeat | `--count 100` systematically reproduces intermittent failures |

**Key insight:** The Python testing ecosystem is mature. Every "we could build a quick version" leads to maintaining test infrastructure instead of testing the actual product.

## Common Pitfalls

### Pitfall 1: pytest-asyncio Mode Confusion
**What goes wrong:** Tests silently skip or fail because asyncio_mode is misconfigured
**Why it happens:** pytest-asyncio has multiple modes (auto, strict, legacy) with different behaviors
**How to avoid:** Orchestra already has `asyncio_mode = "auto"` in pyproject.toml -- keep it. All `async def test_*` functions are automatically treated as async tests.
**Warning signs:** Tests passing when they shouldn't, "PytestUnraisableExceptionWarning" in output

### Pitfall 2: testcontainers Port Conflicts in CI
**What goes wrong:** Container tests fail in CI because ports are already in use
**Why it happens:** testcontainers uses random ports by default, but sometimes Docker host networking causes conflicts
**How to avoid:** Always use `container.get_connection_url()` instead of hardcoded ports. Use `scope="module"` to minimize container churn.
**Warning signs:** "Address already in use" errors, flaky CI runs

### Pitfall 3: Snapshot Drift in CI
**What goes wrong:** Snapshots pass locally but fail in CI (or vice versa)
**Why it happens:** Platform-dependent serialization (line endings, dict ordering, float precision)
**How to avoid:** Syrupy normalizes line endings. For dicts, sort keys in serialization. For floats, round before comparing. Commit `__snapshots__/` directories.
**Warning signs:** "Snapshot does not exist" errors in CI, spurious diffs

### Pitfall 4: Hypothesis Database Location
**What goes wrong:** Hypothesis examples don't reproduce across machines
**Why it happens:** Hypothesis stores its example database in `.hypothesis/` which may not be committed
**How to avoid:** Add `.hypothesis/` to `.gitignore` (examples are machine-specific). Use `@settings(database=None)` for CI if needed.
**Warning signs:** Tests pass locally, fail in CI with different counterexamples

### Pitfall 5: Load Testing Against ScriptedLLM vs Real APIs
**What goes wrong:** Load tests show great performance because they test the mock, not real latency
**Why it happens:** Using ScriptedLLM in load tests bypasses actual I/O bottlenecks
**How to avoid:** Load tests should target the FastAPI server with realistic (or recorded) response latencies. Use `FaultInjector` with `latency_ms=(100, 500)` to simulate real provider latency.
**Warning signs:** Suspiciously fast response times (< 10ms for "LLM calls")

### Pitfall 6: Event Loop per Test vs Shared Loop
**What goes wrong:** Tests interfere with each other's async state
**Why it happens:** pytest-asyncio default is function-scoped loops, but module-scoped fixtures need module-scoped loops
**How to avoid:** Keep default function scope for maximum isolation. If using module-scoped containers, the container fixture itself should be sync (testcontainers handles this).
**Warning signs:** "Event loop is closed" errors, tests passing individually but failing together

### Pitfall 7: Windows Event Loop Policy
**What goes wrong:** Async tests fail on Windows with "NotImplementedError" or "RuntimeError: Event loop is closed"
**Why it happens:** Windows default `ProactorEventLoop` has issues with subprocess and socket operations
**How to avoid:** Add to `conftest.py`:
```python
import sys
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```
**Warning signs:** Tests pass on Linux CI but fail on Windows dev machines

## Code Examples

### Verified: httpx.AsyncClient with FastAPI (from FastAPI official docs)
```python
# Source: https://fastapi.tiangolo.com/advanced/async-tests/
import pytest
from httpx import ASGITransport, AsyncClient
from myapp import app

@pytest.mark.anyio
async def test_root():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        response = await ac.get("/")
    assert response.status_code == 200
```

### Verified: Syrupy Basic Usage (from Syrupy docs)
```python
# Source: https://github.com/syrupy-project/syrupy
# Snapshots stored in __snapshots__/*.ambr files
def test_serialized_event(snapshot):
    result = serialize_event(some_event)
    assert result == snapshot  # First run: creates snapshot. Later: compares.

# Update all snapshots: pytest --snapshot-update
```

### Verified: testcontainers PostgreSQL (from testcontainers docs)
```python
# Source: https://testcontainers.com/guides/getting-started-with-testcontainers-for-python/
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="module")
def postgres():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg

def test_connection(postgres):
    url = postgres.get_connection_url()
    # url is like: postgresql://test:test@localhost:32768/test
```

### Verified: Hypothesis Composite Strategy (from Hypothesis docs)
```python
# Source: https://hypothesis.readthedocs.io/
from hypothesis import given, strategies as st

@st.composite
def sorted_lists(draw):
    xs = draw(st.lists(st.integers()))
    return sorted(xs)

@given(xs=sorted_lists())
def test_is_sorted(xs):
    for i in range(len(xs) - 1):
        assert xs[i] <= xs[i + 1]
```

### Verified: Locust Basic Usage (from locust.io docs)
```python
# Source: https://locust.io/
# Run: locust -f tests/load/locustfile.py --host http://localhost:8000
from locust import HttpUser, task, between

class MyUser(HttpUser):
    wait_time = between(1, 5)

    @task
    def my_task(self):
        self.client.get("/my-endpoint")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `TestClient` (sync) | `httpx.AsyncClient` + `ASGITransport` | FastAPI 0.100+ (2023) | True async testing, no thread pool overhead |
| `pytest-asyncio` strict mode | `asyncio_mode = "auto"` | pytest-asyncio 0.21+ (2023) | No need for `@pytest.mark.asyncio` on every test |
| docker-compose for CI | testcontainers-python | testcontainers 4.x (2024) | Programmatic, no YAML, auto-cleanup, random ports |
| Custom JSON diff | Syrupy snapshots | Syrupy 4.x (2024) | `assert x == snapshot`, automatic update workflow |
| Manual edge case lists | Hypothesis PBT | Stable since 2019 | Finds edge cases humans miss, shrinks to minimal examples |
| Toxiproxy for LLM faults | Custom fault injectors | 2024-2025 pattern | LLM providers don't use TCP proxies; wrap at protocol level |

**Deprecated/outdated:**
- `pytest.fixture(scope="session")` for event loops: Use function scope by default, module scope only when necessary
- `requests` for FastAPI testing: Use `httpx` (async-native, already in Orchestra deps)
- `unittest.mock.patch` for LLM providers: Use `ScriptedLLM` (already in Orchestra) or `FaultInjector` pattern

## Open Questions

1. **Locust vs Real LLM Endpoints**
   - What we know: Locust can test FastAPI endpoints. ScriptedLLM makes responses instant.
   - What's unclear: Should load tests hit real (rate-limited) LLM APIs or simulated endpoints?
   - Recommendation: Use `FaultInjector` with realistic latency (200-2000ms) for load tests. Reserve real API tests for occasional smoke tests with budget caps.

2. **Snapshot Stability for Event Timestamps**
   - What we know: Events have timestamps that differ every run.
   - What's unclear: Best approach for timestamp handling in snapshots.
   - Recommendation: Use Syrupy custom serializer that replaces timestamps with `"<TIMESTAMP>"` placeholder, or use `freezegun` to freeze time in snapshot tests.

3. **CI Docker Availability**
   - What we know: testcontainers requires Docker daemon.
   - What's unclear: Whether GitHub Actions runners have Docker available (they do for ubuntu-latest, not for Windows).
   - Recommendation: Mark container tests with `@pytest.mark.integration` and skip when Docker is unavailable: `pytest.importorskip("docker")`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=8.0 + pytest-asyncio >=0.23 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/unit/ -x -q` |
| Full suite command | `pytest tests/ -x --cov=orchestra` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LOAD-01 | FastAPI handles 100 concurrent users | load | `locust -f tests/load/locustfile.py --headless -u 100 -r 10 -t 60s` | Wave 0 |
| CHAOS-01 | Runner handles provider timeouts | unit | `pytest tests/chaos/test_provider_faults.py -x` | Wave 0 |
| CHAOS-02 | Runner handles malformed responses | unit | `pytest tests/chaos/test_provider_faults.py -x` | Wave 0 |
| REPLAY-01 | Golden file replay matches recorded output | unit | `pytest tests/unit/test_replay_regression.py -x` | Wave 0 |
| SNAP-01 | Event serialization is stable | unit | `pytest tests/unit/test_event_snapshots.py -x` | Wave 0 |
| CONFORM-01 | InMemoryEventStore passes conformance | unit | `pytest tests/conformance/ -x` | Wave 0 |
| CONFORM-02 | SQLiteEventStore passes conformance | unit | `pytest tests/conformance/ -x` | Wave 0 |
| DOCKER-01 | PostgresEventStore works with real Postgres | integration | `pytest tests/integration/test_postgres_integration.py -x` | Wave 0 |
| PROP-01 | Any valid DAG compiles without error | unit | `pytest tests/property/test_graph_topologies.py -x` | Wave 0 |
| CONCUR-01 | Parallel graph runs don't corrupt state | integration | `pytest tests/integration/test_concurrency.py -x` | Wave 0 |
| API-01 | FastAPI endpoints return correct responses | integration | `pytest tests/integration/test_fastapi_endpoints.py -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/unit/ -x -q` (< 30 seconds)
- **Per wave merge:** `pytest tests/ -x --cov=orchestra -m "not slow"` (< 2 minutes)
- **Phase gate:** Full suite including integration: `pytest tests/ --cov=orchestra`

### Wave 0 Gaps
- [ ] `tests/load/locustfile.py` -- Locust load test definitions
- [ ] `tests/chaos/fault_injectors.py` -- Reusable fault injection module
- [ ] `tests/chaos/test_provider_faults.py` -- Fault injection tests
- [ ] `tests/property/test_graph_topologies.py` -- Hypothesis graph generation
- [ ] `tests/conformance/test_eventstore_conformance.py` -- Protocol conformance base class
- [ ] `tests/integration/test_fastapi_endpoints.py` -- FastAPI endpoint tests
- [ ] `tests/integration/test_concurrency.py` -- Concurrent execution tests
- [ ] Install: `pip install locust hypothesis syrupy "testcontainers[postgres,redis]" pytest-repeat asgi-lifespan`
- [ ] `conftest.py` update for Windows event loop policy

## Sources

### Primary (HIGH confidence)
- [FastAPI Official Docs - Async Tests](https://fastapi.tiangolo.com/advanced/async-tests/) -- httpx.AsyncClient pattern
- [Syrupy GitHub](https://github.com/syrupy-project/syrupy) -- snapshot testing API and features
- [Hypothesis Docs](https://hypothesis.readthedocs.io/) -- composite strategies, settings
- [Locust Official](https://locust.io/) -- load testing framework
- [testcontainers-python PyPI](https://pypi.org/project/testcontainers/) -- v4.14.1 (Jan 2026)
- [Toxiproxy GitHub](https://github.com/Shopify/toxiproxy) -- TCP proxy for chaos testing

### Secondary (MEDIUM confidence)
- [Stress Testing FastAPI - KDnuggets](https://www.kdnuggets.com/stress-testing-fastapi-application) -- Locust + FastAPI patterns
- [Testcontainers Getting Started Guide](https://testcontainers.com/guides/getting-started-with-testcontainers-for-python/) -- fixture patterns
- [pytest-asyncio Patterns](https://tonybaloney.github.io/posts/async-test-patterns-for-pytest-and-unittest.html) -- async test patterns
- [LoadForge SSE Testing](https://loadforge.com/directory/real-time-applications/sse) -- SSE load testing patterns
- [Python Free-Threading Guide - Testing](https://py-free-threading.github.io/testing/) -- thread safety validation
- [Deterministic Replay for Trustworthy AI](https://www.sakurasky.com/blog/missing-primitives-for-trustworthy-ai-part-8/) -- replay-driven regression testing

### Tertiary (LOW confidence)
- [LLM Testing in 2025 - Confident AI](https://www.confident-ai.com/blog/llm-testing-in-2024-top-methods-and-strategies) -- general LLM testing strategies (marketing content)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries are well-established, actively maintained, widely adopted
- Architecture: HIGH -- patterns verified against official docs and existing Orchestra codebase
- Pitfalls: HIGH -- based on known issues documented in official repos and community experience
- Load testing patterns: MEDIUM -- SSE-specific Locust patterns have fewer community examples
- Chaos testing for LLM: MEDIUM -- custom fault injectors are a pragmatic pattern but not a formal standard

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable ecosystem, 30-day validity)
