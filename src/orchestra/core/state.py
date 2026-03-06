"""Workflow state with Pydantic + Annotated reducers.

State fields can be annotated with reducer functions that control
how values merge during parallel fan-in. Without a reducer,
last-write-wins semantics apply.

Usage:
    from typing import Annotated
    from orchestra.core.state import WorkflowState, merge_list

    class MyState(WorkflowState):
        messages: Annotated[list[Message], merge_list] = []
        current_agent: str = ""
        step_count: Annotated[int, sum_numbers] = 0
"""

from __future__ import annotations

from typing import Annotated, Any, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from orchestra.core.errors import ReducerError, StateValidationError

# ---- Built-in Reducers (9 total, authoritative names from RECONCILIATION) ----


def merge_list(existing: list[Any], new: list[Any]) -> list[Any]:
    """Append new items to existing list."""
    return existing + new


def merge_dict(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Merge new dict into existing (shallow)."""
    return {**existing, **new}


def sum_numbers(existing: int | float, new: int | float) -> int | float:
    """Add new value to existing."""
    return existing + new


def last_write_wins(existing: Any, new: Any) -> Any:
    """Replace existing with new value."""
    return new


def merge_set(existing: set[Any], new: set[Any]) -> set[Any]:
    """Union of existing and new sets."""
    return existing | new


def concat_str(existing: str, new: str) -> str:
    """Concatenate strings."""
    return existing + new


def keep_first(existing: Any, new: Any) -> Any:
    """Keep the first (existing) value, ignore new."""
    return existing


def max_value(existing: int | float, new: int | float) -> int | float:
    """Keep the maximum of existing and new."""
    return max(existing, new)


def min_value(existing: int | float, new: int | float) -> int | float:
    """Keep the minimum of existing and new."""
    return min(existing, new)


# ---- State Engine ----


class WorkflowState(BaseModel):
    """Base class for typed workflow state with reducer support.

    Subclass this and annotate fields with reducers:

        class MyState(WorkflowState):
            messages: Annotated[list[Message], merge_list] = []
            count: Annotated[int, sum_numbers] = 0
            result: str = ""  # last-write-wins (no reducer)
    """

    model_config = {"arbitrary_types_allowed": True}


def extract_reducers(state_class: type[BaseModel]) -> dict[str, Any]:
    """Extract reducer functions from Annotated type hints.

    For a field like `messages: Annotated[list[Message], merge_list]`,
    this returns {"messages": merge_list}.
    """
    reducers: dict[str, Any] = {}
    hints = get_type_hints(state_class, include_extras=True)

    for field_name, hint in hints.items():
        if get_origin(hint) is Annotated:
            args = get_args(hint)
            for metadata in args[1:]:
                if callable(metadata):
                    reducers[field_name] = metadata
                    break

    return reducers


def apply_state_update(
    state: WorkflowState,
    update: dict[str, Any],
    reducers: dict[str, Any],
) -> WorkflowState:
    """Apply a partial update to state using reducers.

    Fields with reducers: reducer(current_value, new_value)
    Fields without reducers: last-write-wins
    Fields not in update: preserved unchanged

    Returns a NEW state instance (immutable update).
    """
    current_data = state.model_dump()
    new_data = dict(current_data)

    for key, value in update.items():
        if key not in current_data:
            raise StateValidationError(
                f"Unknown state field: '{key}'.\n"
                f"  State class: {state.__class__.__name__}\n"
                f"  Available fields: {list(current_data.keys())}\n"
                f"  Fix: Add '{key}' to your state class or remove it from the update."
            )

        if key in reducers:
            try:
                new_data[key] = reducers[key](current_data[key], value)
            except Exception as e:
                raise ReducerError(
                    f"Reducer '{reducers[key].__name__}' failed on field '{key}'.\n"
                    f"  Existing value: {current_data[key]!r}\n"
                    f"  New value: {value!r}\n"
                    f"  Error: {e}"
                ) from e
        else:
            new_data[key] = value

    try:
        return state.__class__.model_validate(new_data)
    except Exception as e:
        raise StateValidationError(
            f"State validation failed after update.\n"
            f"  State class: {state.__class__.__name__}\n"
            f"  Error: {e}"
        ) from e


def merge_parallel_updates(
    state: WorkflowState,
    updates: list[dict[str, Any]],
    reducers: dict[str, Any],
) -> WorkflowState:
    """Merge multiple parallel updates into state.

    Applies updates sequentially using reducers. For reducer fields,
    all updates accumulate. For non-reducer fields, last update wins.
    """
    result = state
    for update in updates:
        result = apply_state_update(result, update, reducers)
    return result
