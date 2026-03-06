"""Graph edge types.

Edges define transitions between nodes:
- Edge: unconditional A -> B
- ConditionalEdge: A -> B|C|D based on state
- ParallelEdge: A -> [B, C, D] fan-out with join
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

EdgeCondition = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class Edge:
    """Unconditional edge: source always transitions to target."""

    source: str
    target: Any  # str or END sentinel


@dataclass(frozen=True)
class ConditionalEdge:
    """Conditional edge: routes based on a condition function.

    The condition receives state and returns the next node ID (or END).
    If path_map is provided, condition returns a key and path_map maps
    to node IDs.
    """

    source: str
    condition: EdgeCondition
    path_map: dict[str, Any] | None = None

    def resolve(self, state: dict[str, Any]) -> Any:
        result = self.condition(state)
        if self.path_map and isinstance(result, str):
            return self.path_map.get(result, result)
        return result


@dataclass(frozen=True)
class ParallelEdge:
    """Parallel edge: source fans out to multiple targets.

    All targets execute concurrently. Results are merged using
    state reducers before proceeding to join_node.
    """

    source: str
    targets: list[str]
    join_node: Any = None  # str or END sentinel


GraphEdge = Edge | ConditionalEdge | ParallelEdge
