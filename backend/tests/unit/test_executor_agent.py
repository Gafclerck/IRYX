"""Unit tests for ExecutorAgent and procedural tool dispatch (Story 5.5).

Conforms to FR17, D-08, D-09 (deterministic procedural execution, zero LLM calls).
"""

import uuid

import pytest
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from iryx.analytics.models import Observation
from iryx.cases.models import Case, CaseStatus
from iryx.core.exceptions import ToolExecutionTimeoutException
from iryx.evidence.models import Evidence
from iryx.gateway.base import BaseTool, ToolExecutionContext, ToolExecutionResult
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.gateway.registry import ToolRegistry
from iryx.gateway.runner import ToolRunner
from iryx.orchestrator.executor import ExecutorAgent
from iryx.orchestrator.graph import executor_node
from iryx.orchestrator.models import (
    InvestigationStatus,
    Phase,
    PhaseName,
    PhaseStatus,
)
from iryx.orchestrator.schemas import InvestigationPlan, InvestigationPlanStep
from iryx.orchestrator.services import InvestigationService
from iryx.orchestrator.state import InvestigationState


class DummyParams(BaseModel):
    evidence_id: str | uuid.UUID | None = None
    query: str = "default"


class DummySuccessTool(BaseTool):
    name = "dummy_success_tool"
    version = "1.0.0"
    description = "Test success tool"
    timeout_seconds = 10
    parameters_schema = DummyParams

    async def execute(
        self, parameters: DummyParams, context: ToolExecutionContext
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            raw_output={"records": [1, 2, 3]},
            observations=[
                {
                    "source_id": context.evidence_id,
                    "normalized_content": {"key": "test_obs"},
                    "source_location": "line 42",
                }
            ],
            duration_ms=25,
            status=ToolExecutionStatus.SUCCESS,
        )


class DummyFailingTool(BaseTool):
    name = "dummy_failing_tool"
    version = "1.0.0"
    description = "Test failing tool"
    timeout_seconds = 5
    parameters_schema = DummyParams

    async def execute(
        self, parameters: DummyParams, context: ToolExecutionContext
    ) -> ToolExecutionResult:
        raise ToolExecutionTimeoutException("Delai d'attente depasse pour dummy_failing_tool")


def _setup_test_registry() -> ToolRegistry:
    """Create a registry containing dummy test tools."""
    reg = ToolRegistry(enforce_whitelist=False)
    reg.register(DummySuccessTool())
    reg.register(DummyFailingTool())
    return reg


@pytest.fixture
def test_case(db_session: Session) -> Case:
    """Create a test forensic case."""
    case = Case(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        title="Dossier Test Executor",
        description="Investigation pour validation Story 5.5",
        status=CaseStatus.OPEN,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


@pytest.fixture
def sealed_evidence(db_session: Session, test_case: Case) -> Evidence:
    """Create a sealed forensic evidence artifact."""
    ev = Evidence(
        id=uuid.uuid4(),
        case_id=test_case.id,
        original_name="audit_logs.txt",
        file_size=1024,
        detected_type="text",
        sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
    )
    db_session.add(ev)
    db_session.commit()
    db_session.refresh(ev)
    return ev


@pytest.mark.asyncio
async def test_executor_agent_zero_llm_guarantee() -> None:
    """FR17 / D-08: Verify ExecutorAgent never uses or requires an LLM client."""
    reg = _setup_test_registry()
    agent = ExecutorAgent(tool_registry=reg)

    assert not hasattr(agent, "llm_client")
    assert not hasattr(agent, "llm")
    # Instantiation and execution without any LLM configured
    plan = InvestigationPlan(
        summary="Test Plan Zero LLM",
        steps=[
            InvestigationPlanStep(
                step_id=1,
                tool_name="dummy_success_tool",
                target_evidence_id=uuid.uuid4(),
                parameters={"query": "test"},
                rationale="Verification zero LLM",
            )
        ],
    )
    res = await agent.execute(plan=plan, case_id=uuid.uuid4())
    assert res.status == "completed"
    assert res.executed_steps_count == 1
    assert res.error_count == 0


@pytest.mark.asyncio
async def test_executor_agent_nominal_execution() -> None:
    """Verify nominal sequential execution of multiple tools with observation collection."""
    reg = _setup_test_registry()
    runner = ToolRunner(registry=reg)
    agent = ExecutorAgent(tool_runner=runner, tool_registry=reg)

    ev_id1 = uuid.uuid4()
    ev_id2 = uuid.uuid4()

    plan = InvestigationPlan(
        summary="Plan 2 etapes",
        steps=[
            InvestigationPlanStep(
                step_id=1,
                tool_name="dummy_success_tool",
                target_evidence_id=ev_id1,
                parameters={"query": "step1"},
                rationale="Etape 1",
            ),
            InvestigationPlanStep(
                step_id=2,
                tool_name="dummy_success_tool",
                target_evidence_id=ev_id2,
                parameters={"query": "step2"},
                rationale="Etape 2",
            ),
        ],
    )

    case_id = uuid.uuid4()
    result = await agent.execute(plan=plan, case_id=case_id)

    assert result.status == "completed"
    assert result.executed_steps_count == 2
    assert result.total_steps_count == 2
    assert result.error_count == 0
    assert len(result.tool_executions) == 2
    assert len(result.observations) == 2
    assert result.tool_executions[0]["step_id"] == 1
    assert result.tool_executions[1]["step_id"] == 2


@pytest.mark.asyncio
async def test_executor_agent_missing_plan_fails() -> None:
    """Verify executor fails gracefully when no valid plan is supplied."""
    agent = ExecutorAgent()
    result = await agent.execute(plan=None, case_id=uuid.uuid4())

    assert result.status == "failed"
    assert result.error_count == 1
    assert "Aucun plan d'investigation validé" in result.errors[0]


@pytest.mark.asyncio
async def test_executor_agent_invalid_plan_dict() -> None:
    """Verify executor fails when an unparseable plan dictionary is supplied."""
    agent = ExecutorAgent()
    bad_plan = {"steps": "not-a-list"}
    result = await agent.execute(plan=bad_plan, case_id=uuid.uuid4())

    assert result.status == "failed"
    assert result.error_count == 1
    assert "Format de plan d'investigation invalide" in result.errors[0]


@pytest.mark.asyncio
async def test_executor_agent_unknown_tool_rejection() -> None:
    """Verify unknown tools are rejected, logged, and increment error_count."""
    reg = _setup_test_registry()
    agent = ExecutorAgent(tool_registry=reg)

    plan = InvestigationPlan(
        summary="Plan outil inconnu",
        steps=[
            InvestigationPlanStep(
                step_id=1,
                tool_name="malicious_or_unknown_tool",
                target_evidence_id=uuid.uuid4(),
                parameters={},
                rationale="Test outil inconnu",
            ),
            InvestigationPlanStep(
                step_id=2,
                tool_name="dummy_success_tool",
                target_evidence_id=uuid.uuid4(),
                parameters={},
                rationale="Deuxieme etape valide",
            ),
        ],
    )

    result = await agent.execute(plan=plan, case_id=uuid.uuid4())

    # Step 1 fails, but since continue_on_error=True, Step 2 succeeds
    assert result.status == "completed"
    assert result.error_count == 1
    assert result.executed_steps_count == 1
    assert len(result.errors) == 1
    assert "n'est pas enregistré dans la Gateway" in result.errors[0]


@pytest.mark.asyncio
async def test_executor_agent_evidence_validation_in_db(
    db_session: Session, test_case: Case
) -> None:
    """Verify evidence existence and case ownership are strictly rechecked against DB."""
    reg = _setup_test_registry()
    agent = ExecutorAgent(tool_registry=reg, db=db_session)

    other_case_id = uuid.uuid4()
    foreign_evidence = Evidence(
        id=uuid.uuid4(),
        case_id=other_case_id,
        original_name="foreign.evtx",
        file_size=500,
        detected_type="evtx",
        sha256="1111222233334444555566667777888811112222333344445555666677778888",
    )
    db_session.add(foreign_evidence)
    db_session.commit()

    plan = InvestigationPlan(
        summary="Plan preuve étrangère",
        steps=[
            InvestigationPlanStep(
                step_id=1,
                tool_name="dummy_success_tool",
                target_evidence_id=foreign_evidence.id,
                parameters={},
                rationale="Tentative d'accès preuve hors dossier",
            )
        ],
    )

    result = await agent.execute(plan=plan, case_id=test_case.id, db=db_session)

    assert result.status == "completed"
    assert result.error_count == 1
    assert result.executed_steps_count == 0
    assert "n'existe pas ou n'appartient pas au dossier" in result.errors[0]


@pytest.mark.asyncio
async def test_executor_agent_unsealed_evidence_rejection(
    db_session: Session, test_case: Case
) -> None:
    """Verify unsealed evidence (missing SHA-256) is rejected by the Executor."""
    reg = _setup_test_registry()
    agent = ExecutorAgent(tool_registry=reg, db=db_session)

    unsealed_ev = Evidence(
        id=uuid.uuid4(),
        case_id=test_case.id,
        original_name="unsealed.txt",
        file_size=200,
        detected_type="text",
        sha256=None,
    )
    db_session.add(unsealed_ev)
    db_session.commit()

    plan = InvestigationPlan(
        summary="Plan preuve non scellée",
        steps=[
            InvestigationPlanStep(
                step_id=1,
                tool_name="dummy_success_tool",
                target_evidence_id=unsealed_ev.id,
                parameters={},
                rationale="Preuve sans empreinte SHA-256",
            )
        ],
    )

    result = await agent.execute(plan=plan, case_id=test_case.id, db=db_session)

    assert result.status == "completed"
    assert result.error_count == 1
    assert result.executed_steps_count == 0
    assert "n'est pas scellée" in result.errors[0]


@pytest.mark.asyncio
async def test_executor_agent_non_blocking_error_resilience() -> None:
    """Verify non-blocking errors allow remaining steps to execute."""
    reg = _setup_test_registry()
    agent = ExecutorAgent(tool_registry=reg)

    plan = InvestigationPlan(
        summary="Plan résilient",
        steps=[
            InvestigationPlanStep(
                step_id=1,
                tool_name="dummy_failing_tool",
                target_evidence_id=uuid.uuid4(),
                parameters={"is_blocking": False, "continue_on_error": True},
                rationale="Etape 1 en échec",
            ),
            InvestigationPlanStep(
                step_id=2,
                tool_name="dummy_success_tool",
                target_evidence_id=uuid.uuid4(),
                parameters={},
                rationale="Etape 2 nominale",
            ),
        ],
    )

    result = await agent.execute(plan=plan, case_id=uuid.uuid4())

    assert result.status == "completed"
    assert result.error_count == 1
    assert result.executed_steps_count == 1
    assert len(result.errors) == 1
    assert "Delai d'attente depasse" in result.errors[0]
    assert len(result.tool_executions) == 1
    assert result.tool_executions[0]["step_id"] == 2


@pytest.mark.asyncio
async def test_executor_agent_blocking_error_pauses_execution() -> None:
    """Verify blocking error (is_blocking=True) immediately pauses execution and halts step loop."""
    reg = _setup_test_registry()
    agent = ExecutorAgent(tool_registry=reg)

    plan = InvestigationPlan(
        summary="Plan bloquant",
        steps=[
            InvestigationPlanStep(
                step_id=1,
                tool_name="dummy_failing_tool",
                target_evidence_id=uuid.uuid4(),
                parameters={"is_blocking": True},
                rationale="Etape critique",
                is_blocking=True,
            ),
            InvestigationPlanStep(
                step_id=2,
                tool_name="dummy_success_tool",
                target_evidence_id=uuid.uuid4(),
                parameters={},
                rationale="Etape suivante qui ne doit pas tourner",
            ),
        ],
    )

    result = await agent.execute(plan=plan, case_id=uuid.uuid4())

    assert result.status == "paused"
    assert result.error_count == 1
    assert result.executed_steps_count == 0
    assert len(result.tool_executions) == 0
    assert "Delai d'attente depasse" in result.errors[0]


@pytest.mark.asyncio
async def test_executor_agent_full_db_lifecycle_and_phase_transition(
    db_session: Session, test_case: Case, sealed_evidence: Evidence
) -> None:
    """Verify DB phase transition, ToolExecution audit, and Observation persistence."""
    reg = _setup_test_registry()
    service = InvestigationService(db_session)
    run = service.start_investigation(case_id=test_case.id)

    plan = InvestigationPlan(
        summary="Plan persistant DB",
        steps=[
            InvestigationPlanStep(
                step_id=1,
                tool_name="dummy_success_tool",
                target_evidence_id=sealed_evidence.id,
                parameters={"query": "audit"},
                rationale="Analyse de logs",
            )
        ],
    )
    service.save_validated_plan(case_id=test_case.id, run_id=run.id, plan=plan)

    # Set phase to executor for execution
    active_phase = db_session.scalar(
        select(Phase)
        .where(Phase.investigation_run_id == run.id, Phase.status == PhaseStatus.ACTIVE)
    )
    if active_phase:
        active_phase.status = PhaseStatus.COMPLETED
    exec_phase = Phase(
        id=uuid.uuid4(),
        investigation_run_id=run.id,
        phase_name=PhaseName.EXECUTOR,
        status=PhaseStatus.ACTIVE,
    )
    db_session.add(exec_phase)
    run.current_phase = PhaseName.EXECUTOR
    db_session.commit()

    agent = ExecutorAgent(tool_registry=reg, db=db_session)
    result = await agent.execute(
        plan=plan,
        case_id=test_case.id,
        run_id=run.id,
        db=db_session,
    )

    assert result.status == "completed"
    assert result.executed_steps_count == 1
    assert result.error_count == 0

    # Verify DB state
    db_session.refresh(run)
    assert run.current_phase == PhaseName.ANALYST
    assert run.status == InvestigationStatus.RUNNING
    assert run.error_count == 0

    # Verify ToolExecution trace in DB
    tool_execs = list(
        db_session.scalars(
            select(ToolExecution).where(ToolExecution.case_id == test_case.id)
        ).all()
    )
    assert len(tool_execs) == 1
    assert tool_execs[0].tool_name == "dummy_success_tool"
    assert tool_execs[0].agent_role == "Executor"
    assert tool_execs[0].status == ToolExecutionStatus.SUCCESS

    # Verify Observation in DB
    observations = list(
        db_session.scalars(select(Observation).where(Observation.case_id == test_case.id)).all()
    )
    assert len(observations) == 1
    assert observations[0].tool_name == "dummy_success_tool"
    assert observations[0].tool_execution_id == tool_execs[0].id


@pytest.mark.asyncio
async def test_executor_agent_db_pause_on_blocking_failure(
    db_session: Session, test_case: Case, sealed_evidence: Evidence
) -> None:
    """Verify DB status is set to PAUSED when a blocking error occurs."""
    reg = _setup_test_registry()
    service = InvestigationService(db_session)
    run = service.start_investigation(case_id=test_case.id)

    plan = InvestigationPlan(
        summary="Plan blocage DB",
        steps=[
            InvestigationPlanStep(
                step_id=1,
                tool_name="dummy_failing_tool",
                target_evidence_id=sealed_evidence.id,
                parameters={"is_blocking": True},
                rationale="Etape critique qui echoue",
                is_blocking=True,
            )
        ],
    )
    service.save_validated_plan(case_id=test_case.id, run_id=run.id, plan=plan)

    agent = ExecutorAgent(tool_registry=reg, db=db_session)
    result = await agent.execute(
        plan=plan,
        case_id=test_case.id,
        run_id=run.id,
        db=db_session,
    )

    assert result.status == "paused"
    assert result.error_count == 1

    db_session.refresh(run)
    assert run.status == InvestigationStatus.PAUSED
    assert run.current_phase == PhaseName.EXECUTOR
    assert run.error_count == 1


def test_executor_agent_sync_execution() -> None:
    """Verify execute_sync runs synchronously without raising event loop conflict."""
    reg = _setup_test_registry()
    agent = ExecutorAgent(tool_registry=reg)

    plan = InvestigationPlan(
        summary="Sync plan",
        steps=[
            InvestigationPlanStep(
                step_id=1,
                tool_name="dummy_success_tool",
                target_evidence_id=uuid.uuid4(),
                parameters={},
                rationale="Test synchrone",
            )
        ],
    )
    result = agent.execute_sync(plan=plan, case_id=uuid.uuid4())
    assert result.status == "completed"
    assert result.executed_steps_count == 1


def test_executor_node_in_graph_success() -> None:
    """Verify executor_node transitions state to analyst and populates executions/observations."""
    reg = _setup_test_registry()
    state: InvestigationState = {
        "case_id": str(uuid.uuid4()),
        "run_id": str(uuid.uuid4()),
        "plan": {
            "summary": "Plan pour graph node",
            "steps": [
                {
                    "step_id": 1,
                    "tool_name": "dummy_success_tool",
                    "target_evidence_id": str(uuid.uuid4()),
                    "parameters": {},
                    "rationale": "Analyse graph",
                }
            ],
        },
        "error_count": 0,
        "context": {"tool_registry": reg},
    }

    update = executor_node(state)
    assert update["current_phase"] == "analyst"
    assert update["status"] == "running"
    assert update["error_count"] == 0
    assert len(update["tool_executions"]) == 1
    assert len(update["observations"]) == 1
