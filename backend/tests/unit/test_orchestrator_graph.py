"""Unit tests for LangGraph state graph compilation, streaming, checkpointer, and planner."""

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END
from langgraph.graph.state import CompiledStateGraph

from iryx.ai.client import UnifiedLLMClient
from iryx.ai.schemas import LLMResponse
from iryx.orchestrator.graph import (
    analyst_node,
    build_investigation_graph,
    executor_node,
    gate_h1_node,
    gate_h2_node,
    gate_h3_node,
    planner_node,
    reporting_node,
    route_analyst,
    route_executor,
    route_gate_h1,
    route_gate_h2,
    route_planner,
    route_verifier,
    triage_node,
    verifier_node,
)
from iryx.orchestrator.state import InvestigationState

EXPECTED_NODES = {
    "triage",
    "planner",
    "gate_h1",
    "executor",
    "analyst",
    "verifier",
    "gate_h2",
    "gate_h3",
    "reporting",
}


def _create_sample_pre_set_plan() -> dict[str, Any]:
    """Helper returning a valid pre-set investigation plan dict."""
    return {
        "summary": "Valid pre-set test plan",
        "steps": [
            {
                "step_id": 1,
                "tool_name": "parse_evtx",
                "target_evidence_id": str(uuid.uuid4()),
                "parameters": {},
                "rationale": "Valid step rationale",
            }
        ],
    }


def test_build_investigation_graph_compiles_successfully() -> None:
    """Verify build_investigation_graph compiles and contains all 9 required nodes."""
    graph = build_investigation_graph()
    assert isinstance(graph, CompiledStateGraph)

    # Validate that all 9 required nodes are present in the compiled graph
    graph_node_names = set(graph.nodes.keys())
    assert EXPECTED_NODES.issubset(graph_node_names)
    assert len(EXPECTED_NODES.intersection(graph_node_names)) == 9


def test_node_functions_return_expected_updates() -> None:
    """Verify each node function updates state correctly."""
    state_without_evidence: InvestigationState = {
        "case_id": "test-case-id",
        "run_id": "test-run-id",
        "iteration_count": 0,
        "error_count": 0,
    }

    assert triage_node(state_without_evidence) == {"current_phase": "triage"}

    # Planner without evidence short-circuits and pauses (without populating errors)
    planner_result = planner_node(state_without_evidence)
    assert planner_result["current_phase"] == "planner"
    assert planner_result["status"] == "paused"
    assert planner_result["plan"] is None
    assert "notification" in planner_result.get("context", {})
    assert "errors" not in planner_result

    # Gate H1 automatically suspends when unapproved
    assert gate_h1_node(state_without_evidence) == {
        "current_phase": "waiting_h1",
        "status": "paused",
    }
    # Gate H1 advances when approved
    assert gate_h1_node({"h1_approved": True}) == {
        "current_phase": "gate_h1",
        "status": "running",
        "h1_approved": True,
    }
    # Gate H1 loops back when rejected with replanning
    replan_res = gate_h1_node({"h1_rejected": True, "return_to_planner": True})
    assert replan_res["current_phase"] == "planner"
    assert replan_res["status"] == "running"
    assert replan_res["plan"] is None
    assert replan_res["h1_rejected"] is False
    assert replan_res["return_to_planner"] is False
    # Gate H1 terminates when rejected without replanning
    assert gate_h1_node({"h1_rejected": True, "return_to_planner": False}) == {
        "current_phase": "gate_h1",
        "status": "completed",
        "h1_rejected": True,
    }

    # Executor node with missing plan sets failed status
    executor_res = executor_node(state_without_evidence)
    assert executor_res["current_phase"] == "executor"
    assert executor_res["status"] == "failed"
    assert len(executor_res["errors"]) >= 1

    # Analyst node with no observations transitions to verifier
    analyst_res = analyst_node(state_without_evidence)
    assert analyst_res["current_phase"] == "verifier"
    assert analyst_res["status"] == "running"
    assert "notification" in analyst_res.get("context", {})

    # Verifier and human gate nodes
    assert verifier_node(state_without_evidence) == {
        "current_phase": "gate_h2",
        "status": "running",
    }
    assert gate_h2_node(state_without_evidence) == {
        "current_phase": "waiting_h2",
        "status": "paused",
    }
    assert gate_h2_node({"h2_approved": True}) == {
        "current_phase": "gate_h2",
        "status": "running",
        "h2_approved": True,
    }
    assert gate_h2_node({"h2_rejected": True}) == {
        "current_phase": "gate_h2",
        "status": "completed",
        "h2_rejected": True,
    }
    assert gate_h3_node(state_without_evidence) == {"current_phase": "gate_h3"}
    assert reporting_node(state_without_evidence) == {"current_phase": "reporting"}


def test_planner_node_with_pre_set_plan() -> None:
    """Verify planner_node validates pre-set plan and advances to gate_h1."""
    valid_plan = _create_sample_pre_set_plan()
    state_with_plan: InvestigationState = {
        "case_id": "test-case-id",
        "run_id": "test-run-id",
        "plan": valid_plan,
        "iteration_count": 0,
        "error_count": 0,
    }

    result = planner_node(state_with_plan)
    assert result["current_phase"] == "gate_h1"
    assert result["status"] == "running"
    assert result["plan"]["summary"] == "Valid pre-set test plan"


def test_planner_node_rejects_invalid_pre_set_plan() -> None:
    """Verify planner_node marks status as failed when pre-set plan is invalid."""
    state_with_bad_plan: InvestigationState = {
        "case_id": "test-case-id",
        "run_id": "test-run-id",
        "plan": {
            "summary": "Empty plan without steps",
            "steps": [],
        },
        "iteration_count": 0,
        "error_count": 0,
    }

    result = planner_node(state_with_bad_plan)
    assert result["current_phase"] == "planner"
    assert result["status"] == "failed"
    assert result["plan"] is None
    assert len(result["errors"]) >= 1


def test_planner_node_catches_invalid_plan_exception() -> None:
    """Verify planner_node catches InvalidPlanException from agent and sets failed status."""
    mock_llm = MagicMock(spec=UnifiedLLMClient)
    # Return broken outputs exhausting retries
    mock_llm.complete = AsyncMock(
        side_effect=[
            LLMResponse(content="invalid 1", role="assistant", model="m"),
            LLMResponse(content="invalid 2", role="assistant", model="m"),
            LLMResponse(content="invalid 3", role="assistant", model="m"),
        ]
    )

    state: InvestigationState = {
        "case_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "evidences": [
            {
                "id": str(uuid.uuid4()),
                "original_name": "test.evtx",
                "file_size": 100,
                "detected_type": "evtx",
                "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            }
        ],
        "context": {"llm_client": mock_llm},
    }

    result = planner_node(state)
    assert result["current_phase"] == "planner"
    assert result["status"] == "failed"
    assert result["plan"] is None
    assert len(result["errors"]) == 1
    assert "2 tentatives de correction" in result["errors"][0]


def test_planner_node_with_sealed_evidence_and_mock_llm() -> None:
    """Verify planner_node generates a validated plan and transitions to gate_h1."""
    evidence_id = str(uuid.uuid4())
    mock_llm = MagicMock(spec=UnifiedLLMClient)
    mock_llm.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(
                {
                    "summary": "Plan de test généré",
                    "steps": [
                        {
                            "step_id": 1,
                            "tool_name": "parse_evtx",
                            "target_evidence_id": evidence_id,
                            "parameters": {},
                            "rationale": "Analyse des logs d'authentification.",
                        }
                    ],
                }
            ),
            role="assistant",
            model="mock-model",
            total_tokens=50,
        )
    )

    state: InvestigationState = {
        "case_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "evidences": [
            {
                "id": evidence_id,
                "original_name": "Security.evtx",
                "file_size": 2048,
                "detected_type": "application/x-ms-evtx",
                "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            }
        ],
        "context": {"llm_client": mock_llm},
    }

    result = planner_node(state)
    assert result["current_phase"] == "gate_h1"
    assert result["status"] == "running"
    assert result["plan"] is not None
    assert len(result["plan"]["steps"]) == 1
    assert result["plan"]["steps"][0]["tool_name"] == "parse_evtx"


def test_route_planner_conditional_edge() -> None:
    """Verify route_planner halts at END when paused or failed, and gate_h1 otherwise."""
    assert route_planner({"status": "paused"}) == END
    assert route_planner({"status": "failed"}) == END
    assert route_planner({"status": "running"}) == "gate_h1"
    assert route_planner({}) == "gate_h1"


def test_route_gate_h1_conditional_edge() -> None:
    """Verify route_gate_h1 routes to executor when approved, planner when replan, else END."""
    assert route_gate_h1({"h1_approved": True}) == "executor"
    assert route_gate_h1({"return_to_planner": True}) == "planner"
    assert route_gate_h1({"h1_rejected": True, "return_to_planner": True}) == "planner"
    assert route_gate_h1({"h1_rejected": True, "return_to_planner": False}) == END
    assert route_gate_h1({"status": "paused"}) == END
    assert route_gate_h1({}) == END


def test_route_executor_conditional_edge() -> None:
    """Verify route_executor routes to analyst when running, and END when paused or failed."""
    assert route_executor({"status": "running"}) == "analyst"
    assert route_executor({"status": "completed"}) == "analyst"
    assert route_executor({"status": "paused"}) == END
    assert route_executor({"status": "failed"}) == END


def test_route_analyst_conditional_edge() -> None:
    """Verify route_analyst routes to verifier when running, and END when paused or failed."""
    assert route_analyst({"status": "running"}) == "verifier"
    assert route_analyst({"status": "completed"}) == "verifier"
    assert route_analyst({"status": "paused"}) == END
    assert route_analyst({"status": "failed"}) == END
    assert route_analyst({}) == "verifier"


def test_route_verifier_conditional_edge() -> None:
    """Verify route_verifier routes to gate_h2 when running, and END when paused or failed."""
    assert route_verifier({"status": "running"}) == "gate_h2"
    assert route_verifier({"status": "completed"}) == "gate_h2"
    assert route_verifier({"status": "paused"}) == END
    assert route_verifier({"status": "failed"}) == END
    assert route_verifier({}) == "gate_h2"


def test_analyst_node_with_observations_and_mock_llm() -> None:
    """Verify analyst_node parses observations, invokes AnalystAgent, and updates findings."""
    obs_id = str(uuid.uuid4())
    tool_id = str(uuid.uuid4())
    mock_llm = MagicMock(spec=UnifiedLLMClient)
    mock_llm.complete = AsyncMock(
        return_value=LLMResponse(
            content=json.dumps(
                {
                    "summary": "Constat généré avec succès.",
                    "findings": [
                        {
                            "title": "Exécution d'outil suspect",
                            "severity": "high",
                            "confidence": "high",
                            "finding_type": "fact",
                            "observation_refs": [obs_id],
                            "tool_execution_refs": [tool_id],
                        }
                    ],
                }
            ),
            role="assistant",
            model="mock-model",
        )
    )

    state: InvestigationState = {
        "case_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "observations": [
            {
                "id": obs_id,
                "tool_name": "parse_evtx",
                "tool_execution_id": tool_id,
                "normalized_content": {"event_id": 4688},
            }
        ],
        "context": {"llm_client": mock_llm},
    }

    result = analyst_node(state)
    assert result["current_phase"] == "verifier"
    assert result["status"] == "running"
    assert "findings" in result
    assert len(result["findings"]) == 1
    assert result["findings"][0]["title"] == "Exécution d'outil suspect"
    assert result["findings"][0]["severity"] == "high"
    assert result["findings"][0]["observation_refs"] == [obs_id]


def test_analyst_node_failure_propagates_error() -> None:
    """Verify analyst_node sets failed status and records errors on persistent failure."""
    obs_id = str(uuid.uuid4())
    tool_id = str(uuid.uuid4())
    mock_llm = MagicMock(spec=UnifiedLLMClient)
    mock_llm.complete = AsyncMock(
        side_effect=[
            LLMResponse(content="bad 1", role="assistant", model="m"),
            LLMResponse(content="bad 2", role="assistant", model="m"),
            LLMResponse(content="bad 3", role="assistant", model="m"),
        ]
    )

    state: InvestigationState = {
        "case_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "observations": [
            {
                "id": obs_id,
                "tool_name": "parse_evtx",
                "tool_execution_id": tool_id,
                "normalized_content": {},
            }
        ],
        "context": {"llm_client": mock_llm},
    }

    result = analyst_node(state)
    assert result["current_phase"] == "analyst"
    assert result["status"] == "failed"
    assert len(result["errors"]) >= 1
    assert "findings" not in result or len(result.get("findings", [])) == 0


def test_verifier_node_empty_findings_advances_to_gate_h2() -> None:
    """Verify verifier_node with no findings immediately advances to gate_h2."""
    state: InvestigationState = {
        "case_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "findings": [],
        "iteration_count": 0,
        "error_count": 0,
    }
    result = verifier_node(state)
    assert result["current_phase"] == "gate_h2"
    assert result["status"] == "running"


def test_verifier_node_missing_db_with_findings_fails() -> None:
    """Verify verifier_node fails if findings are present but DB session is absent."""
    state: InvestigationState = {
        "case_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "findings": [
            {
                "title": "Finding sans DB",
                "observation_refs": [str(uuid.uuid4())],
                "tool_execution_refs": [str(uuid.uuid4())],
            }
        ],
        "iteration_count": 0,
        "error_count": 0,
    }
    result = verifier_node(state)
    assert result["current_phase"] == "verifier"
    assert result["status"] == "failed"
    assert len(result["errors"]) >= 1


def test_verifier_node_with_db_verifies_and_updates_findings() -> None:
    """Verify verifier_node certifies valid findings and invalidates hallucinations."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from iryx.analytics.models import Finding, FindingStatus, Observation
    from iryx.auth.models import Organization, User
    from iryx.cases.models import Case
    from iryx.db.base import Base
    from iryx.gateway.models import ToolExecution, ToolExecutionStatus

    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    org = Organization(name="Test Org")
    session.add(org)
    session.flush()

    user = User(email="test@soc.fr", hashed_password="pw")
    session.add(user)
    session.flush()

    case = Case(title="Case Verifier Test", organization_id=org.id, created_by=user.id)
    session.add(case)
    session.flush()

    tool = ToolExecution(
        case_id=case.id,
        tool_name="parse_evtx",
        tool_version="1.0.0",
        agent_role="executor",
        status=ToolExecutionStatus.SUCCESS,
    )
    session.add(tool)
    session.flush()

    obs = Observation(
        case_id=case.id,
        tool_name="parse_evtx",
        tool_execution_id=tool.id,
        normalized_content={"event_id": 4688},
    )
    session.add(obs)
    session.flush()

    # Finding 1: Valid
    f1 = Finding(
        case_id=case.id,
        title="Finding Valide",
        status=FindingStatus.PROPOSED,
        observation_refs=[obs.id],
        tool_execution_refs=[tool.id],
    )
    # Finding 2: Hallucinated
    fake_obs_id = uuid.uuid4()
    f2 = Finding(
        case_id=case.id,
        title="Finding Hallucine",
        status=FindingStatus.PROPOSED,
        observation_refs=[fake_obs_id],
        tool_execution_refs=[tool.id],
    )
    session.add_all([f1, f2])
    session.commit()

    state: InvestigationState = {
        "case_id": str(case.id),
        "run_id": str(uuid.uuid4()),
        "findings": [
            {
                "id": str(f1.id),
                "title": f1.title,
                "observation_refs": [str(obs.id)],
                "tool_execution_refs": [str(tool.id)],
            },
            {
                "id": str(f2.id),
                "title": f2.title,
                "observation_refs": [str(fake_obs_id)],
                "tool_execution_refs": [str(tool.id)],
            },
        ],
        "context": {"db": session},
        "iteration_count": 0,
        "error_count": 0,
    }

    result = verifier_node(state)
    assert result["current_phase"] == "gate_h2"
    assert result["status"] == "running"
    assert "findings" in result
    assert len(result["findings"]) == 2

    # Check finding 1 is certified
    f1_res = next(f for f in result["findings"] if f["title"] == "Finding Valide")
    assert f1_res["status"] == "proposed"
    assert f1_res["is_verified"] is True

    # Check finding 2 is rejected
    f2_res = next(f for f in result["findings"] if f["title"] == "Finding Hallucine")
    assert f2_res["status"] == "rejected"
    assert f2_res["is_verified"] is False
    assert f2_res["rejection_reason"] == "HALLUCINATED_REFERENCE_DETECTED"

    # Verify DB persistence
    session.refresh(f1)
    session.refresh(f2)
    assert f1.status == FindingStatus.PROPOSED
    assert f2.status == FindingStatus.REJECTED

    session.close()
    Base.metadata.drop_all(bind=engine)


def test_graph_execution_halts_when_no_sealed_evidence() -> None:
    """Verify graph executes triage -> planner and halts at END when no evidence is present."""
    graph = build_investigation_graph()
    initial_state: InvestigationState = {
        "case_id": "test-case-no-evidence",
        "run_id": "test-run-no-evidence",
        "iteration_count": 0,
        "error_count": 0,
    }

    result = graph.invoke(initial_state)
    assert isinstance(result, dict)
    assert result.get("current_phase") == "planner"
    assert result.get("status") == "paused"
    assert result.get("plan") is None


def test_graph_suspends_automatically_at_gate_h1() -> None:
    """Verify that reaching gate_h1 automatically suspends execution with status: paused."""
    graph = build_investigation_graph()
    initial_state: InvestigationState = {
        "case_id": "test-case-123",
        "run_id": "test-run-456",
        "plan": _create_sample_pre_set_plan(),
        "iteration_count": 0,
        "error_count": 0,
    }

    result = graph.invoke(initial_state)
    assert isinstance(result, dict)
    assert result.get("current_phase") == "waiting_h1"
    assert result.get("status") == "paused"
    assert result.get("case_id") == "test-case-123"


def test_graph_execution_flow_with_approved_plan() -> None:
    """Verify execution flows through executor to reporting when h1_approved is True."""
    graph = build_investigation_graph()
    initial_state: InvestigationState = {
        "case_id": "test-case-123",
        "run_id": "test-run-456",
        "plan": _create_sample_pre_set_plan(),
        "h1_approved": True,
        "h2_approved": True,
        "iteration_count": 0,
        "error_count": 0,
    }

    result = graph.invoke(initial_state)
    assert isinstance(result, dict)
    assert result.get("current_phase") == "reporting"
    assert result.get("case_id") == "test-case-123"


def test_graph_sequential_stream_nodes() -> None:
    """VG-3: Verify via stream that all 9 nodes are traversed sequentially when approved."""
    graph = build_investigation_graph()
    initial_state: InvestigationState = {
        "case_id": "stream-case",
        "run_id": "stream-run",
        "plan": _create_sample_pre_set_plan(),
        "h1_approved": True,
        "h2_approved": True,
        "iteration_count": 0,
        "error_count": 0,
    }

    traversed_nodes: list[str] = []
    for event in graph.stream(initial_state):
        for node_name in event:
            traversed_nodes.append(node_name)

    expected_sequence = [
        "triage",
        "planner",
        "gate_h1",
        "executor",
        "analyst",
        "verifier",
        "gate_h2",
        "gate_h3",
        "reporting",
    ]
    assert traversed_nodes == expected_sequence


def test_graph_stream_halts_at_gate_h1_when_unapproved() -> None:
    """Verify via graph.stream that execution stops at gate_h1 when not approved."""
    graph = build_investigation_graph()
    initial_state: InvestigationState = {
        "case_id": "stream-case-pause",
        "run_id": "stream-run-pause",
        "plan": _create_sample_pre_set_plan(),
        "iteration_count": 0,
        "error_count": 0,
    }

    traversed_nodes: list[str] = []
    for event in graph.stream(initial_state):
        for node_name in event:
            traversed_nodes.append(node_name)

    assert traversed_nodes == ["triage", "planner", "gate_h1"]


def test_graph_rebouclage_planner_when_rejected_with_replan() -> None:
    """Verify via graph.stream that rejection with replan loops back to planner."""
    graph = build_investigation_graph()
    initial_state: InvestigationState = {
        "case_id": "replan-case",
        "run_id": "replan-run",
        "plan": _create_sample_pre_set_plan(),
        "h1_rejected": True,
        "return_to_planner": True,
        "iteration_count": 0,
        "error_count": 0,
    }

    traversed_nodes: list[str] = []
    for event in graph.stream(initial_state):
        for node_name in event:
            traversed_nodes.append(node_name)

    assert traversed_nodes == ["triage", "planner", "gate_h1", "planner"]


def test_gate_h1_node_persists_pause_when_db_in_context() -> None:
    """Verify gate_h1_node invokes pause_at_gate_h1 when db session is in context."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from iryx.auth.schemas import UserCreate
    from iryx.auth.services import UserService
    from iryx.cases.services import CaseService
    from iryx.db.base import Base
    from iryx.orchestrator.models import InvestigationStatus, PhaseName
    from iryx.orchestrator.services import InvestigationService
    from iryx.organizations.services import OrganizationService

    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    user_svc = UserService(session)
    org_svc = OrganizationService(session)
    case_svc = CaseService(session)
    user = user_svc.create_user(UserCreate(email="lead@soc.fr", password="Password123!"))
    org = org_svc.create_organization(name="SOC Lab", creator_id=user.id)
    case = case_svc.create_case(
        org_id=org.id,
        title="Test Case",
        description="Test Case Description",
        creator_id=user.id,
    )

    inv_svc = InvestigationService(session)
    run = inv_svc.start_investigation(case.id)
    assert run.status == InvestigationStatus.RUNNING

    state: InvestigationState = {
        "case_id": str(case.id),
        "run_id": str(run.id),
        "context": {"db": session},
        "iteration_count": 0,
        "error_count": 0,
    }

    res = gate_h1_node(state)
    assert res["current_phase"] == "waiting_h1"
    assert res["status"] == "paused"

    session.refresh(run)
    assert run.status == InvestigationStatus.PAUSED
    assert run.current_phase == PhaseName.WAITING_H1

    session.close()
    Base.metadata.drop_all(bind=engine)


def test_graph_compilation_with_checkpointer() -> None:
    """BH-16: Verify graph compiles and executes successfully with a MemorySaver checkpointer."""
    checkpointer = MemorySaver()
    graph = build_investigation_graph(checkpointer=checkpointer)
    assert isinstance(graph, CompiledStateGraph)

    initial_state: InvestigationState = {
        "case_id": "checkpointer-case",
        "run_id": "checkpointer-run",
        "plan": _create_sample_pre_set_plan(),
        "h1_approved": True,
        "h2_approved": True,
        "iteration_count": 0,
        "error_count": 0,
    }
    config = {"configurable": {"thread_id": "thread-investigation-1"}}

    result = graph.invoke(initial_state, config=config)
    assert result["current_phase"] == "reporting"
    assert result["case_id"] == "checkpointer-case"

    # Verify state snapshot is persisted in the checkpointer
    state_snapshot = graph.get_state(config)
    assert state_snapshot is not None
    assert state_snapshot.values["current_phase"] == "reporting"


def test_gate_h2_node_and_route_gate_h2() -> None:
    """Verify route_gate_h2 routes to gate_h3 when h2_approved is True, else END."""
    assert route_gate_h2({"h2_approved": True}) == "gate_h3"
    assert route_gate_h2({"h2_rejected": True}) == END
    assert route_gate_h2({"status": "paused"}) == END
    assert route_gate_h2({}) == END


def test_graph_stream_halts_at_gate_h2_when_unapproved() -> None:
    """Verify via graph.stream that execution stops at gate_h2 when h2_approved is not set."""
    graph = build_investigation_graph()
    initial_state: InvestigationState = {
        "case_id": "stream-case-h2-pause",
        "run_id": "stream-run-h2-pause",
        "plan": _create_sample_pre_set_plan(),
        "h1_approved": True,
        "iteration_count": 0,
        "error_count": 0,
    }

    traversed_nodes: list[str] = []
    for event in graph.stream(initial_state):
        for node_name in event:
            traversed_nodes.append(node_name)

    expected_sequence = [
        "triage",
        "planner",
        "gate_h1",
        "executor",
        "analyst",
        "verifier",
        "gate_h2",
    ]
    assert traversed_nodes == expected_sequence


def test_gate_h2_node_persists_pause_when_db_in_context() -> None:
    """Verify gate_h2_node invokes pause_at_gate_h2 when db session is in context."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from iryx.auth.schemas import UserCreate
    from iryx.auth.services import UserService
    from iryx.cases.services import CaseService
    from iryx.db.base import Base
    from iryx.orchestrator.models import InvestigationStatus, PhaseName
    from iryx.orchestrator.services import InvestigationService
    from iryx.organizations.services import OrganizationService

    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    user_svc = UserService(session)
    org_svc = OrganizationService(session)
    case_svc = CaseService(session)
    user = user_svc.create_user(UserCreate(email="analyst-h2@soc.fr", password="Password123!"))
    org = org_svc.create_organization(name="SOC Lab H2", creator_id=user.id)
    case = case_svc.create_case(
        org_id=org.id,
        title="Test Case H2",
        description="Test Case Description H2",
        creator_id=user.id,
    )

    inv_svc = InvestigationService(session)
    run = inv_svc.start_investigation(case.id)
    assert run.status == InvestigationStatus.RUNNING

    state: InvestigationState = {
        "case_id": str(case.id),
        "run_id": str(run.id),
        "context": {"db": session},
        "iteration_count": 0,
        "error_count": 0,
    }

    res = gate_h2_node(state)
    assert res["current_phase"] == "waiting_h2"
    assert res["status"] == "paused"

    session.refresh(run)
    assert run.status == InvestigationStatus.PAUSED
    assert run.current_phase == PhaseName.WAITING_H2

    session.close()
    Base.metadata.drop_all(bind=engine)
