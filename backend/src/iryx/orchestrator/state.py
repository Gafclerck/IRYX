"""TypedDict schema representing the state for LangGraph investigation graph."""

import operator
from typing import Annotated, Any, TypedDict


class InvestigationState(TypedDict, total=False):
    """Investigation graph execution state shared across all nodes."""

    case_id: str
    run_id: str
    status: str
    current_phase: str
    plan: dict[str, Any] | None
    tool_executions: Annotated[list[dict[str, Any]], operator.add]
    observations: Annotated[list[dict[str, Any]], operator.add]
    findings: Annotated[list[dict[str, Any]], operator.add]
    iteration_count: int
    error_count: int
    errors: Annotated[list[str], operator.add]
    report: dict[str, Any] | None
    h1_approved: bool
    h1_rejected: bool
    return_to_planner: bool
    h2_approved: bool
    h3_approved: bool
    context: dict[str, Any]
