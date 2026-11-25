"""Unit tests for LangGraph state graph compilation, streaming, and checkpointer integration."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph

from iryx.orchestrator.graph import (
    analyst_node,
    build_investigation_graph,
    executor_node,
    gate_h1_node,
    gate_h2_node,
    gate_h3_node,
    planner_node,
    reporting_node,
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


def test_build_investigation_graph_compiles_successfully() -> None:
    """Verify build_investigation_graph compiles and contains all 9 required nodes."""
    graph = build_investigation_graph()
    assert isinstance(graph, CompiledStateGraph)

    # Validate that all 9 required nodes are present in the compiled graph
    graph_node_names = set(graph.nodes.keys())
    assert EXPECTED_NODES.issubset(graph_node_names)
    assert len(EXPECTED_NODES.intersection(graph_node_names)) == 9


def test_node_functions_return_expected_updates() -> None:
    """Verify each node function updates current_phase correctly."""
    state: InvestigationState = {
        "case_id": "test-case-id",
        "run_id": "test-run-id",
        "iteration_count": 0,
        "error_count": 0,
    }

    assert triage_node(state) == {"current_phase": "triage"}
    assert planner_node(state) == {"current_phase": "planner"}
    assert gate_h1_node(state) == {"current_phase": "gate_h1"}
    assert executor_node(state) == {"current_phase": "executor"}
    assert analyst_node(state) == {"current_phase": "analyst"}
    assert verifier_node(state) == {"current_phase": "verifier"}
    assert gate_h2_node(state) == {"current_phase": "gate_h2"}
    assert gate_h3_node(state) == {"current_phase": "gate_h3"}
    assert reporting_node(state) == {"current_phase": "reporting"}


def test_graph_execution_flow() -> None:
    """Verify execution of the linear scaffolding flow through all 9 nodes to reporting."""
    graph = build_investigation_graph()
    initial_state: InvestigationState = {
        "case_id": "test-case-123",
        "run_id": "test-run-456",
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
