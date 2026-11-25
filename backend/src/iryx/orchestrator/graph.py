"""LangGraph state graph initialization and compilation for digital forensics investigation."""

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from iryx.orchestrator.state import InvestigationState

# 9 Required Nodes:
# triage, planner, gate_h1, executor, analyst, verifier, gate_h2, gate_h3, reporting


def triage_node(state: InvestigationState) -> dict[str, Any]:
    """Triage phase: initial qualification of evidence and incident scope."""
    return {"current_phase": "triage"}


def planner_node(state: InvestigationState) -> dict[str, Any]:
    """Planner phase: proposes a bounded investigation plan."""
    return {"current_phase": "planner"}


def gate_h1_node(state: InvestigationState) -> dict[str, Any]:
    """Human Gate H1: analyst reviews and arbitrates the proposed plan."""
    return {"current_phase": "gate_h1"}


def executor_node(state: InvestigationState) -> dict[str, Any]:
    """Executor phase: deterministic execution of approved forensic tools."""
    return {"current_phase": "executor"}


def analyst_node(state: InvestigationState) -> dict[str, Any]:
    """Analyst phase: contextual interpretation of forensic observations."""
    return {"current_phase": "analyst"}


def verifier_node(state: InvestigationState) -> dict[str, Any]:
    """Verifier phase: adversarial checks and verification of hypotheses."""
    return {"current_phase": "verifier"}


def gate_h2_node(state: InvestigationState) -> dict[str, Any]:
    """Human Gate H2: validation of intermediate findings."""
    return {"current_phase": "gate_h2"}


def gate_h3_node(state: InvestigationState) -> dict[str, Any]:
    """Human Gate H3: final validation before official report export."""
    return {"current_phase": "gate_h3"}


def reporting_node(state: InvestigationState) -> dict[str, Any]:
    """Reporting phase: synthesis and generation of sealed incident report."""
    return {"current_phase": "reporting"}


def build_investigation_graph(checkpointer: Any | None = None) -> CompiledStateGraph:
    """Build and compile the LangGraph investigation state graph with the 9 mandatory nodes."""
    workflow = StateGraph(InvestigationState)

    # Register all 9 nodes
    workflow.add_node("triage", triage_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("gate_h1", gate_h1_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("verifier", verifier_node)
    workflow.add_node("gate_h2", gate_h2_node)
    workflow.add_node("gate_h3", gate_h3_node)
    workflow.add_node("reporting", reporting_node)

    # Scaffolding edges
    workflow.add_edge(START, "triage")
    workflow.add_edge("triage", "planner")
    workflow.add_edge("planner", "gate_h1")
    workflow.add_edge("gate_h1", "executor")
    workflow.add_edge("executor", "analyst")
    workflow.add_edge("analyst", "verifier")
    workflow.add_edge("verifier", "gate_h2")
    workflow.add_edge("gate_h2", "gate_h3")
    workflow.add_edge("gate_h3", "reporting")
    workflow.add_edge("reporting", END)

    return workflow.compile(checkpointer=checkpointer)
