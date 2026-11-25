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
    """Planner phase: proposes a bounded investigation plan (Story 5.3)."""
    from iryx.core.exceptions import InvalidPlanException
    from iryx.orchestrator.planner import PlannerAgent
    from iryx.orchestrator.schemas import InvestigationPlan

    context = dict(state.get("context") or {})
    llm_client = context.get("llm_client")
    tool_registry = context.get("tool_registry")
    db = context.get("db")

    # If plan is already provided in state, validate against InvestigationPlan
    if state.get("plan") is not None:
        try:
            validated = InvestigationPlan.model_validate(state["plan"])
            return {
                "current_phase": "gate_h1",
                "status": state.get("status", "running"),
                "plan": validated.model_dump(mode="json"),
            }
        except Exception as exc:
            return {
                "current_phase": "planner",
                "status": "failed",
                "plan": None,
                "errors": [str(exc)],
            }

    evidences = state.get("evidences") or context.get("evidences")
    case_id = state.get("case_id")
    run_id = state.get("run_id")

    agent = PlannerAgent(
        llm_client=llm_client,
        tool_registry=tool_registry,
        db=db,
    )

    try:
        result = agent.plan_sync(
            evidences=evidences,
            case_id=case_id,
            run_id=run_id,
            db=db,
        )
    except InvalidPlanException as exc:
        return {
            "current_phase": "planner",
            "status": "failed",
            "plan": None,
            "errors": [str(exc)],
            "context": context,
        }

    if result.status == "paused" or result.plan is None:
        notification = (
            result.notification or "Aucune matière analysable : attente de preuves scellées."
        )
        return {
            "current_phase": "planner",
            "status": "paused",
            "plan": None,
            "context": {**context, "notification": notification},
        }

    plan_dict = result.plan.model_dump(mode="json")
    return {
        "current_phase": "gate_h1",
        "status": "running",
        "plan": plan_dict,
        "context": context,
    }


def route_planner(state: InvestigationState) -> str:
    """Conditional edge from planner: halt execution if paused or failed, else gate_h1."""
    if state.get("status") in ("paused", "failed"):
        return END
    return "gate_h1"


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
    workflow.add_conditional_edges(
        "planner",
        route_planner,
        {
            "gate_h1": "gate_h1",
            END: END,
        },
    )
    workflow.add_edge("gate_h1", "executor")
    workflow.add_edge("executor", "analyst")
    workflow.add_edge("analyst", "verifier")
    workflow.add_edge("verifier", "gate_h2")
    workflow.add_edge("gate_h2", "gate_h3")
    workflow.add_edge("gate_h3", "reporting")
    workflow.add_edge("reporting", END)

    return workflow.compile(checkpointer=checkpointer)
