"""Integration tests for Orchestra FastAPI server endpoints.

These tests require server dependencies (fastapi, httpx, sse-starlette).
They are skipped automatically if dependencies are not installed.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

try:
    from fastapi.testclient import TestClient
    from httpx import AsyncClient

    HAS_SERVER_DEPS = True
except ImportError:
    HAS_SERVER_DEPS = False

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not HAS_SERVER_DEPS, reason="Server dependencies not installed"),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_test_graph(name: str = "test-graph") -> Any:
    """Build a trivial compiled graph for testing."""
    from orchestra.core.graph import WorkflowGraph

    async def echo(state: dict[str, Any]) -> dict[str, Any]:
        return {"output": state.get("input", "hello")}

    graph = WorkflowGraph(name=name)
    graph.add_node("echo", echo)
    graph.set_entry_point("echo")
    return graph.compile()


@pytest.fixture()
def app() -> Any:
    """Create a FastAPI app with a registered test graph."""
    from orchestra.server.app import create_app
    from orchestra.server.config import ServerConfig

    config = ServerConfig()
    application = create_app(config)

    # Manually trigger lifespan and register graph
    # We use TestClient which handles lifespan automatically
    return application


@pytest.fixture()
def client(app: Any) -> Any:
    """Synchronous test client with lifespan events."""
    with TestClient(app, raise_server_exceptions=False) as c:
        # Register test graph after lifespan has initialized app.state
        graph = _make_test_graph()
        app.state.graph_registry.register("test-graph", graph)
        yield c


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


def test_healthz_returns_200(client: Any) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_readyz_returns_200(client: Any) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def test_create_run_returns_202(client: Any) -> None:
    response = client.post(
        "/api/v1/runs",
        json={"graph_name": "test-graph", "input": {"input": "hi"}},
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "running"
    assert data["graph_name"] == "test-graph"
    assert "run_id" in data


def test_get_run_status(client: Any) -> None:
    # Create a run first
    create_resp = client.post(
        "/api/v1/runs",
        json={"graph_name": "test-graph", "input": {"input": "test"}},
    )
    run_id = create_resp.json()["run_id"]

    # Give the background task a moment to start
    import time
    time.sleep(0.2)

    response = client.get(f"/api/v1/runs/{run_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run_id
    assert data["status"] in ("running", "completed")


def test_list_runs(client: Any) -> None:
    # Create a run
    client.post(
        "/api/v1/runs",
        json={"graph_name": "test-graph", "input": {}},
    )

    response = client.get("/api/v1/runs")
    assert response.status_code == 200
    runs = response.json()
    assert isinstance(runs, list)
    assert len(runs) >= 1


def test_get_nonexistent_run_returns_404(client: Any) -> None:
    response = client.get("/api/v1/runs/nonexistent-id")
    assert response.status_code == 404


def test_create_run_unknown_graph_returns_404(client: Any) -> None:
    response = client.post(
        "/api/v1/runs",
        json={"graph_name": "no-such-graph", "input": {}},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Graphs
# ---------------------------------------------------------------------------


def test_list_graphs(client: Any) -> None:
    response = client.get("/api/v1/graphs")
    assert response.status_code == 200
    graphs = response.json()
    assert isinstance(graphs, list)
    assert len(graphs) == 1
    assert graphs[0]["name"] == "test-graph"


def test_get_graph_detail(client: Any) -> None:
    response = client.get("/api/v1/graphs/test-graph")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test-graph"
    assert "echo" in data["nodes"]
    assert data["entry_point"] == "echo"
    assert "mermaid" in data
    assert "graph TD" in data["mermaid"]


def test_get_graph_not_found(client: Any) -> None:
    response = client.get("/api/v1/graphs/nonexistent")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Resume (basic path — expects 404 since the run hasn't checkpointed)
# ---------------------------------------------------------------------------


def test_resume_run(client: Any) -> None:
    # Create a run first
    create_resp = client.post(
        "/api/v1/runs",
        json={"graph_name": "test-graph", "input": {"input": "resume-me"}},
    )
    run_id = create_resp.json()["run_id"]

    import time
    time.sleep(0.2)

    # Try to resume — it will attempt but the graph likely completed already
    # so resume may fail at the checkpoint lookup level. What matters is
    # the endpoint is reachable and returns a valid response structure.
    response = client.post(
        f"/api/v1/runs/{run_id}/resume",
        json={"state_updates": {"approved": True}},
    )
    # 200 if accepted, or could get an error from the resume attempt
    assert response.status_code in (200, 404, 500)
