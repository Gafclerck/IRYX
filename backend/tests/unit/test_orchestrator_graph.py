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
    route_planner,
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

    # Other nodes
    assert gate_h1_node(state_without_evidence) == {"current_phase": "gate_h1"}
    assert executor_node(state_without_evidence) == {"current_phase": "executor"}
    assert analyst_node(state_without_evidence) == {"current_phase": "analyst"}
    assert verifier_node(state_without_evidence) == {"current_phase": "verifier"}
    assert gate_h2_node(state_without_evidence) == {"current_phase": "gate_h2"}
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


def test_graph_execution_flow_with_pre_set_plan() -> None:
    """Verify execution of the linear scaffolding flow through all 9 nodes to reporting."""
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
    assert result.get("current_phase") == "reporting"
    assert result.get("case_id") == "test-case-123"


def test_graph_sequential_stream_nodes() -> None:
    """VG-3: Verify via graph.stream that all 9 nodes are traversed in exact sequential order."""
    graph = build_investigation_graph()
    initial_state: InvestigationState = {
        "case_id": "stream-case",
        "run_id": "stream-run",
        "plan": _create_sample_pre_set_plan(),
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


def test_graph_compilation_with_checkpointer() -> None:
    """BH-16: Verify graph compiles and executes successfully with a MemorySaver checkpointer."""
    checkpointer = MemorySaver()
    graph = build_investigation_graph(checkpointer=checkpointer)
    assert isinstance(graph, CompiledStateGraph)

    initial_state: InvestigationState = {
        "case_id": "checkpointer-case",
        "run_id": "checkpointer-run",
        "plan": _create_sample_pre_set_plan(),
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
