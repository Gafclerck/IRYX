"""LangGraph state graph initialization and compilation for digital forensics investigation."""

import contextvars
import logging
import uuid
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from iryx.orchestrator.state import InvestigationState

logger = logging.getLogger("iryx.orchestrator.graph")

_runtime_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "_runtime_context", default=None
)


def set_runtime_context(ctx: dict[str, Any]) -> None:
    """Set transient runtime dependencies (e.g. db, tool_runner) for graph nodes."""
    _runtime_context.set(ctx)


def get_runtime_context() -> dict[str, Any]:
    """Retrieve transient runtime dependencies."""
    return _runtime_context.get() or {}


def _sanitize_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Strip non-serializable runtime objects so checkpointers can serialize state."""
    non_serializable_keys = {"db", "tool_registry", "tool_runner", "llm_client"}
    return {k: v for k, v in ctx.items() if k not in non_serializable_keys}


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

    runtime_ctx = get_runtime_context()
    context = dict(state.get("context") or {})
    llm_client = context.get("llm_client") or runtime_ctx.get("llm_client")
    tool_registry = context.get("tool_registry") or runtime_ctx.get("tool_registry")
    db = context.get("db") or runtime_ctx.get("db")

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

    replan_feedback = context.get("replan_feedback")
    base_desc = context.get("incident_description") or state.get("incident_description") or ""
    if replan_feedback:
        incident_desc = f"{base_desc}\nFeedback analyste : {replan_feedback}".strip()
    else:
        incident_desc = base_desc

    try:
        result = agent.plan_sync(
            evidences=evidences,
            case_id=case_id,
            run_id=run_id,
            incident_description=incident_desc,
            db=db,
        )
    except InvalidPlanException as exc:
        return {
            "current_phase": "planner",
            "status": "failed",
            "plan": None,
            "errors": [str(exc)],
            "context": _sanitize_context(context),
        }

    if result.status == "paused" or result.plan is None:
        notification = (
            result.notification or "Aucune matière analysable : attente de preuves scellées."
        )
        return {
            "current_phase": "planner",
            "status": "paused",
            "plan": None,
            "context": _sanitize_context({**context, "notification": notification}),
        }

    plan_dict = result.plan.model_dump(mode="json")
    return {
        "current_phase": "gate_h1",
        "status": "running",
        "plan": plan_dict,
        "context": _sanitize_context(context),
    }


def route_planner(state: InvestigationState) -> str:
    """Conditional edge from planner: halt execution if paused or failed, else gate_h1."""
    if state.get("status") in ("paused", "failed"):
        return END
    return "gate_h1"


def gate_h1_node(state: InvestigationState) -> dict[str, Any]:
    """Human Gate H1: analyst reviews and arbitrates the proposed plan.

    Automatically suspends execution awaiting analyst arbitration (status: paused,
    current_phase: waiting_h1). When h1_approved is True, unblocks execution towards
    the executor node.
    """
    context = dict(state.get("context") or {})

    if state.get("h1_approved"):
        return {
            "current_phase": "gate_h1",
            "status": "running",
            "h1_approved": True,
        }
    if state.get("h1_rejected"):
        if state.get("return_to_planner"):
            feedback = (
                state.get("feedback") or context.get("feedback") or context.get("replan_feedback")
            )
            updated_context = dict(context)
            if feedback:
                updated_context["replan_feedback"] = feedback
            return {
                "current_phase": "planner",
                "status": "running",
                "plan": None,
                "h1_rejected": False,
                "return_to_planner": False,
                "context": updated_context,
            }
        return {
            "current_phase": "gate_h1",
            "status": "completed",
            "h1_rejected": True,
        }

    # Automatically suspend execution at Gate H1
    runtime_ctx = get_runtime_context()
    db = context.get("db") or runtime_ctx.get("db")
    case_id = state.get("case_id")
    run_id = state.get("run_id")

    if db is not None and case_id is not None and run_id is not None:
        try:
            from iryx.orchestrator.services import InvestigationService

            case_uuid = uuid.UUID(str(case_id))
            run_uuid = uuid.UUID(str(run_id))
            InvestigationService(db).pause_at_gate_h1(case_id=case_uuid, run_id=run_uuid)
        except Exception as exc:
            logger.warning("Could not persist gate_h1 paused state in DB: %s", exc)
    else:
        logger.debug(
            "DB session or identifiers omitted from context during gate_h1 pause",
            extra={
                "context": {
                    "has_db": db is not None,
                    "case_id": str(case_id) if case_id else None,
                    "run_id": str(run_id) if run_id else None,
                }
            },
        )

    return {
        "current_phase": "waiting_h1",
        "status": "paused",
    }


def route_gate_h1(state: InvestigationState) -> str:
    """Conditional edge from gate_h1: route to executor if approved, planner if replan, else END."""
    if state.get("h1_approved"):
        return "executor"
    if state.get("return_to_planner") or state.get("current_phase") == "planner":
        return "planner"
    return END


def executor_node(state: InvestigationState) -> dict[str, Any]:
    """Executor phase: deterministic execution of approved forensic tools (Story 5.5).

    Strictly zero LLM calls. Executes steps sequentially via ToolRunner / Gateway.
    Transitions to analyst phase upon completion.
    """
    from iryx.orchestrator.executor import ExecutorAgent

    runtime_ctx = get_runtime_context()
    context = dict(state.get("context") or {})
    db = context.get("db") or runtime_ctx.get("db")
    tool_registry = context.get("tool_registry") or runtime_ctx.get("tool_registry")
    tool_runner = context.get("tool_runner") or runtime_ctx.get("tool_runner")

    agent = ExecutorAgent(
        tool_runner=tool_runner,
        tool_registry=tool_registry,
        db=db,
    )

    case_id = state.get("case_id")
    run_id = state.get("run_id")
    plan = state.get("plan")

    result = agent.execute_sync(
        plan=plan,
        case_id=case_id,
        run_id=run_id,
        db=db,
    )

    next_phase = "analyst" if result.status == "completed" else "executor"
    next_status = "running" if result.status == "completed" else result.status

    update: dict[str, Any] = {
        "current_phase": next_phase,
        "status": next_status,
        "error_count": state.get("error_count", 0) + result.error_count,
    }
    if result.tool_executions:
        update["tool_executions"] = result.tool_executions
    if result.observations:
        update["observations"] = result.observations
    if result.errors:
        update["errors"] = result.errors

    return update


def route_executor(state: InvestigationState) -> str:
    """Conditional edge from executor: route to analyst if running, else END if paused or failed."""
    if state.get("status") in ("paused", "failed"):
        return END
    return "analyst"


def analyst_node(state: InvestigationState) -> dict[str, Any]:
    """Analyst phase: contextual interpretation of forensic observations (Story 6.2, FR22)."""
    from iryx.orchestrator.analyst import AnalystAgent

    runtime_ctx = get_runtime_context()
    context = dict(state.get("context") or {})
    llm_client = context.get("llm_client") or runtime_ctx.get("llm_client")
    db = context.get("db") or runtime_ctx.get("db")

    agent = AnalystAgent(
        llm_client=llm_client,
        db=db,
    )

    case_id = state.get("case_id")
    run_id = state.get("run_id")
    observations = state.get("observations") or context.get("observations")
    tool_executions = state.get("tool_executions") or context.get("tool_executions")
    incident_desc = context.get("incident_description") or state.get("incident_description") or ""

    result = agent.analyze_sync(
        observations=observations,
        tool_executions=tool_executions,
        case_id=case_id,
        run_id=run_id,
        incident_description=incident_desc,
        db=db,
    )

    next_phase = "verifier" if result.status == "completed" else "analyst"
    next_status = "running" if result.status == "completed" else result.status

    update: dict[str, Any] = {
        "current_phase": next_phase,
        "status": next_status,
    }

    if result.findings:
        findings_dicts = [
            f.model_dump(mode="json") if hasattr(f, "model_dump") else dict(f)
            for f in result.findings
        ]
        update["findings"] = findings_dicts

    if result.notification:
        updated_context = dict(context)
        updated_context["notification"] = result.notification
        update["context"] = _sanitize_context(updated_context)
    else:
        update["context"] = _sanitize_context(context)

    if result.errors:
        update["errors"] = result.errors

    return update


def route_analyst(state: InvestigationState) -> str:
    """Conditional edge from analyst: route to verifier if running, else END if paused or failed."""
    if state.get("status") in ("paused", "failed"):
        return END
    return "verifier"


def verifier_node(state: InvestigationState) -> dict[str, Any]:
    """Verifier phase: deterministic formal verification without LLM (Story 6.3, FR23, NFR-REL-01).

    Validates that each observation_ref and tool_execution_ref exists in the database
    and belongs strictly to the current case_id.
    """
    from iryx.orchestrator.verifier import FindingVerifier, VerificationStatus

    runtime_ctx = get_runtime_context()
    context = dict(state.get("context") or {})
    db = context.get("db") or runtime_ctx.get("db")
    case_id = state.get("case_id")
    findings = state.get("findings") or context.get("findings")

    verifier = FindingVerifier(db=db)
    result = verifier.verify_sync(
        findings=findings,
        case_id=case_id,
        db=db,
    )

    if result.status == VerificationStatus.FAILED:
        return {
            "current_phase": "verifier",
            "status": "failed",
            "errors": result.errors,
        }

    update: dict[str, Any] = {
        "current_phase": "gate_h2",
        "status": "running",
    }

    if result.findings:
        update["findings"] = result.findings

    if result.errors:
        update["errors"] = result.errors

    return update


def route_verifier(state: InvestigationState) -> str:
    """Conditional edge from verifier: route to gate_h2 if running, else END if paused or failed."""
    if state.get("status") in ("paused", "failed"):
        return END
    return "gate_h2"


def gate_h2_node(state: InvestigationState) -> dict[str, Any]:
    """Human Gate H2: validation of intermediate findings (Story 6.4, FR19).

    Automatically suspends execution awaiting analyst arbitration (status: paused,
    current_phase: waiting_h2). When h2_approved is True, unblocks execution towards
    the gate_h3 node. When h2_rejected is True, terminates execution.
    """
    context = dict(state.get("context") or {})

    if state.get("h2_approved"):
        return {
            "current_phase": "gate_h2",
            "status": "running",
            "h2_approved": True,
        }
    if state.get("h2_rejected"):
        return {
            "current_phase": "gate_h2",
            "status": "completed",
            "h2_rejected": True,
        }

    # Automatically suspend execution at Gate H2
    runtime_ctx = get_runtime_context()
    db = context.get("db") or runtime_ctx.get("db")
    case_id = state.get("case_id")
    run_id = state.get("run_id")

    if db is not None and case_id is not None and run_id is not None:
        try:
            from iryx.orchestrator.services import InvestigationService

            case_uuid = uuid.UUID(str(case_id))
            run_uuid = uuid.UUID(str(run_id))
            InvestigationService(db).pause_at_gate_h2(case_id=case_uuid, run_id=run_uuid)
        except Exception as exc:
            logger.warning("Could not persist gate_h2 paused state in DB: %s", exc)
    else:
        logger.debug(
            "DB session or identifiers omitted from context during gate_h2 pause",
            extra={
                "context": {
                    "has_db": db is not None,
                    "case_id": str(case_id) if case_id else None,
                    "run_id": str(run_id) if run_id else None,
                }
            },
        )

    return {
        "current_phase": "waiting_h2",
        "status": "paused",
    }


def route_gate_h2(state: InvestigationState) -> str:
    """Conditional edge from gate_h2: route to gate_h3 if approved, else END."""
    if state.get("h2_approved"):
        return "gate_h3"
    return END


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
    workflow.add_conditional_edges(
        "gate_h1",
        route_gate_h1,
        {
            "executor": "executor",
            "planner": "planner",
            END: END,
        },
    )
    workflow.add_conditional_edges(
        "executor",
        route_executor,
        {
            "analyst": "analyst",
            END: END,
        },
    )
    workflow.add_conditional_edges(
        "analyst",
        route_analyst,
        {
            "verifier": "verifier",
            END: END,
        },
    )
    workflow.add_conditional_edges(
        "verifier",
        route_verifier,
        {
            "gate_h2": "gate_h2",
            END: END,
        },
    )
    workflow.add_conditional_edges(
        "gate_h2",
        route_gate_h2,
        {
            "gate_h3": "gate_h3",
            END: END,
        },
    )
    workflow.add_edge("gate_h3", "reporting")
    workflow.add_edge("reporting", END)

    return workflow.compile(checkpointer=checkpointer)
