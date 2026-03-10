"""FastAPI dependency injection functions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

    from orchestra.server.lifecycle import GraphRegistry, RunManager
    from orchestra.storage.store import EventStore


def get_graph_registry(request: "Request") -> "GraphRegistry":
    """Return the GraphRegistry from app state."""
    return request.app.state.graph_registry  # type: ignore[no-any-return]


def get_run_manager(request: "Request") -> "RunManager":
    """Return the RunManager from app state."""
    return request.app.state.run_manager  # type: ignore[no-any-return]


def get_event_store(request: "Request") -> "EventStore":
    """Return the EventStore from app state."""
    return request.app.state.event_store  # type: ignore[no-any-return]
