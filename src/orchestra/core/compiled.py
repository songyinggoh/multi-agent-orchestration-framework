"""CompiledGraph execution engine.

The CompiledGraph is the runtime engine. It takes a validated graph
structure and executes it against a state instance, routing through
edges and applying state updates via reducers.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog

from orchestra.core.context import ExecutionContext
from orchestra.core.edges import ConditionalEdge, Edge, ParallelEdge
from orchestra.core.errors import AgentError, GraphCompileError, MaxIterationsError
from orchestra.core.nodes import AgentNode, FunctionNode, GraphNode, SubgraphNode
from orchestra.core.state import (
    WorkflowState,
    apply_state_update,
    extract_reducers,
    merge_parallel_updates,
)
from orchestra.core.types import END, AgentResult

logger = structlog.get_logger(__name__)


class CompiledGraph:
    """Executable workflow graph.

    Created by WorkflowGraph.compile(). Runs the graph against
    a state instance, following edges and applying state updates.
    """

    def __init__(
        self,
        nodes: dict[str, GraphNode],
        edges: list[Edge | ConditionalEdge | ParallelEdge],
        entry_point: str,
        state_schema: type[Any] | None = None,
        max_turns: int = 50,
        name: str = "",
    ) -> None:
        self._nodes = nodes
        self._edges = edges
        self._entry_point = entry_point
        self._state_schema = state_schema
        self._max_turns = max_turns
        self._name = name

        # Pre-compute edge lookup
        self._edge_map: dict[str, list[Edge | ConditionalEdge | ParallelEdge]] = {}
        for edge in edges:
            source = edge.source
            self._edge_map.setdefault(source, []).append(edge)

        # Extract reducers
        self._reducers: dict[str, Any] = {}
        if state_schema:
            self._reducers = extract_reducers(state_schema)

    async def run(
        self,
        initial_state: dict[str, Any] | WorkflowState | None = None,
        *,
        input: str | dict[str, Any] | None = None,
        context: ExecutionContext | None = None,
        provider: Any = None,
    ) -> dict[str, Any]:
        """Execute the graph from entry point to completion.

        Args:
            initial_state: Starting state (dict or WorkflowState).
            input: Shorthand for initial state (string becomes {"input": value}).
            context: Optional execution context.
            provider: Optional LLM provider (injected into agent contexts).

        Returns:
            Final state as a dict.
        """
        # Resolve initial state
        raw_state = self._resolve_initial_state(initial_state, input)

        # Create or use execution context
        if context is None:
            context = ExecutionContext(
                run_id=uuid.uuid4().hex,
                provider=provider,
            )
        elif provider is not None:
            context.provider = provider

        # Normalize to WorkflowState if schema provided
        if self._state_schema and isinstance(raw_state, dict):
            state: WorkflowState | dict[str, Any] = self._state_schema.model_validate(raw_state)
        elif isinstance(raw_state, WorkflowState):
            state = raw_state
        else:
            state = raw_state

        current_node_id: Any = self._entry_point
        turns = 0
        node_execution_order: list[str] = []

        while (current_node_id != END and not isinstance(current_node_id, type(END))
               and turns < self._max_turns):
            turns += 1
            context.turn_number = turns
            context.node_id = str(current_node_id)

            node = self._nodes.get(str(current_node_id))
            if node is None:
                raise GraphCompileError(
                    f"Node '{current_node_id}' not found during execution.\n"
                    f"  Available nodes: {list(self._nodes.keys())}"
                )

            logger.debug("executing_node", node=current_node_id, turn=turns)

            # Execute the node
            state_dict = state.model_dump() if isinstance(state, WorkflowState) else dict(state)
            context.state = state_dict

            update = await self._execute_node(str(current_node_id), node, state_dict, context)
            node_execution_order.append(str(current_node_id))

            # Apply state update
            if update:
                if isinstance(state, WorkflowState):
                    state = apply_state_update(state, update, self._reducers)
                else:
                    state.update(update)

            # Determine next node (parallel execution may update state)
            state_dict = state.model_dump() if isinstance(state, WorkflowState) else dict(state)
            current_node_id, state = await self._resolve_next(
                str(current_node_id), state_dict, state, context
            )

        if (turns >= self._max_turns and current_node_id != END
                and not isinstance(current_node_id, type(END))):
            raise MaxIterationsError(
                f"Workflow exceeded max_turns ({self._max_turns}).\n"
                f"  Last node: {current_node_id}\n"
                f"  Fix: Increase max_turns or add an exit condition to your loop."
            )

        result = state.model_dump() if isinstance(state, WorkflowState) else dict(state)
        result["__node_execution_order__"] = node_execution_order
        return result

    def _resolve_initial_state(
        self,
        initial_state: dict[str, Any] | WorkflowState | None,
        input: str | dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Resolve initial state from various input types."""
        if initial_state is not None:
            if isinstance(initial_state, WorkflowState):
                return initial_state.model_dump()
            return dict(initial_state)

        if input is not None:
            if isinstance(input, str):
                return {"input": input}
            return dict(input)

        return {}

    async def _execute_node(
        self,
        node_id: str,
        node: GraphNode,
        state_dict: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Execute a single node and return state update."""
        try:
            if isinstance(node, AgentNode):
                return await self._execute_agent_node(node_id, node, state_dict, context)
            elif isinstance(node, (FunctionNode, SubgraphNode)):
                return await node(state_dict)
            else:
                # Generic callable
                if callable(node):
                    return await node(state_dict)
                raise AgentError(f"Node '{node_id}' is not callable: {type(node)}")
        except (AgentError, GraphCompileError):
            raise
        except Exception as e:
            raise AgentError(
                f"Node '{node_id}' failed: {e}\n"
                f"  Node type: {type(node).__name__}"
            ) from e

    async def _execute_agent_node(
        self,
        node_id: str,
        node: AgentNode,
        state_dict: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Execute an AgentNode using the 3-layer merge strategy."""
        agent = node.agent

        # Prepare input
        if node.input_mapper:
            agent_input = node.input_mapper(state_dict)
        else:
            # Default: pass messages from state, or the full input
            messages = state_dict.get("messages", [])
            if isinstance(messages, list) and messages:
                agent_input: Any = messages
            else:
                # Build a simple user message from available state
                input_text = state_dict.get("input", "")
                if not input_text:
                    # Use the last output as input
                    input_text = state_dict.get("output", "")
                agent_input = input_text or ""

        # Execute agent
        result: AgentResult = await agent.run(agent_input, context)

        # Custom output mapper overrides everything
        if node.output_mapper:
            return node.output_mapper(result)

        # 3-layer merge strategy
        update: dict[str, Any] = {}

        # Layer 1: explicit state_updates
        if result.state_updates:
            update.update(result.state_updates)

        # Layer 2: output -> designated state field
        output_key = node.output_key or f"{node_id}_output"
        if result.output:
            # If state has "output" field (common simple case), write there too
            if "output" in (self._state_schema.model_fields if self._state_schema else {}):
                update["output"] = result.output
            update[output_key] = result.output

        # Layer 3: structured output field mapping (opt-in)
        if node.map_output and result.structured_output and self._state_schema:
            output_dict = result.structured_output.model_dump()
            state_fields = set(self._state_schema.model_fields.keys())
            for field_name, field_value in output_dict.items():
                if field_name in state_fields:
                    update[field_name] = field_value

        # Always merge messages if state has a messages field
        if result.messages:
            state_fields = set(
                self._state_schema.model_fields.keys() if self._state_schema else state_dict.keys()
            )
            if "messages" in state_fields:
                update["messages"] = result.messages

        return update

    async def _resolve_next(
        self,
        current_node_id: str,
        state_dict: dict[str, Any],
        state: WorkflowState | dict[str, Any],
        context: ExecutionContext,
    ) -> tuple[Any, WorkflowState | dict[str, Any]]:
        """Determine the next node based on outgoing edges.

        Returns (next_node_id, updated_state). State may change during
        parallel execution.
        """
        edges = self._edge_map.get(current_node_id, [])

        if not edges:
            return END, state

        for edge in edges:
            if isinstance(edge, Edge):
                return edge.target, state

            elif isinstance(edge, ConditionalEdge):
                result = edge.resolve(state_dict)
                return result, state

            elif isinstance(edge, ParallelEdge):
                new_state = await self._execute_parallel(
                    edge, state_dict, state, context
                )
                next_node = edge.join_node if edge.join_node is not None else END
                return next_node, new_state

        return END, state

    async def _execute_parallel(
        self,
        edge: ParallelEdge,
        state_dict: dict[str, Any],
        state: WorkflowState | dict[str, Any],
        context: ExecutionContext,
    ) -> WorkflowState | dict[str, Any]:
        """Execute parallel targets concurrently and merge results.

        Returns a new state instance (preserves immutability).
        """
        tasks = []
        for target_id in edge.targets:
            node = self._nodes[target_id]
            tasks.append(
                self._execute_node(target_id, node, dict(state_dict), context)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            raise AgentError(
                f"Parallel execution failed.\n"
                f"  Failed nodes: {[str(e) for e in errors]}"
            ) from errors[0]

        updates = [r for r in results if isinstance(r, dict)]

        if isinstance(state, WorkflowState):
            return merge_parallel_updates(state, updates, self._reducers)
        else:
            merged = dict(state)
            for update in updates:
                merged.update(update)
            return merged

    def to_mermaid(self) -> str:
        """Generate a Mermaid diagram of the graph.

        Returns Mermaid syntax that renders in GitHub, VS Code, and docs.
        """
        lines = ["graph TD"]

        # Add nodes
        for node_id, node in self._nodes.items():
            if isinstance(node, AgentNode):
                agent_name = getattr(node.agent, "name", node_id)
                lines.append(f'    {node_id}["{agent_name}"]')
            elif isinstance(node, FunctionNode):
                lines.append(f'    {node_id}[/"{node_id}"/]')
            else:
                lines.append(f'    {node_id}["{node_id}"]')

        # Mark entry point
        lines.append(f"    __start__((Start)) --> {self._entry_point}")

        # Add edges
        for edge in self._edges:
            if isinstance(edge, Edge):
                target = "END" if edge.target == END or edge.target is END else edge.target
                if target == "END":
                    lines.append(f"    {edge.source} --> __end__((End))")
                else:
                    lines.append(f"    {edge.source} --> {target}")
            elif isinstance(edge, ConditionalEdge):
                if edge.path_map:
                    for label, target in edge.path_map.items():
                        t = "END" if target == END or target is END else target
                        if t == "END":
                            lines.append(f"    {edge.source} -->|{label}| __end__((End))")
                        else:
                            lines.append(f"    {edge.source} -->|{label}| {t}")
                else:
                    lines.append(f"    {edge.source} -.->|condition| ???")
            elif isinstance(edge, ParallelEdge):
                for target in edge.targets:
                    lines.append(f"    {edge.source} --> {target}")
                if edge.join_node and edge.join_node != END:
                    for target in edge.targets:
                        lines.append(f"    {target} --> {edge.join_node}")

        return "\n".join(lines)
