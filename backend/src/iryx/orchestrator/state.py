"""TypedDict schema representing the state for LangGraph investigation graph."""

import operator
from typing import Annotated, Any, TypedDict


def merge_findings(
    left: list[dict[str, Any]] | None,
    right: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Reducer merging findings by ID or title while preserving new additions and updates."""
    if left is None:
        return list(right or [])
    if right is None:
        return list(left)

    merged: dict[str, dict[str, Any]] = {}
    unkeyed: list[dict[str, Any]] = []

    for item in left:
        key = str(item.get("id") or item.get("title") or "").strip()
        if key:
            merged[key] = dict(item)
        else:
            unkeyed.append(dict(item))

    for item in right:
        key = str(item.get("id") or item.get("title") or "").strip()
        if key:
            if key in merged:
                merged[key].update(item)
            else:
                merged[key] = dict(item)
        else:
            unkeyed.append(dict(item))

    return list(merged.values()) + unkeyed


class InvestigationState(TypedDict, total=False):
    """Investigation graph execution state shared across all nodes."""

    case_id: str
    run_id: str
    status: str
    current_phase: str
    plan: dict[str, Any] | None
    tool_executions: Annotated[list[dict[str, Any]], operator.add]
    observations: Annotated[list[dict[str, Any]], operator.add]
    findings: Annotated[list[dict[str, Any]], merge_findings]
    iteration_count: int
    error_count: int
    errors: Annotated[list[str], operator.add]
    report: dict[str, Any] | None
    h1_approved: bool
    h1_rejected: bool
    return_to_planner: bool
    h2_approved: bool
    h2_rejected: bool
    h3_approved: bool
    context: dict[str, Any]
