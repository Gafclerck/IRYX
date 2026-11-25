"""Unit tests for Checkpointer and Investigation Resume (Story 5.6 / FR21).

Validates:
- Checkpointer factory behaviour (PostgresSaver URL normalization, MemorySaver in test/SQLite)
- Process-wide reset_memory_saver utility
- State persistence and snapshot retrieval across LangGraph nodes
- Strict session thread_id partitioning (no cross-run collision)
- InvestigationService.resume_investigation nominal execution
- CannotResumeTerminatedSessionException on completed session (400)
- CannotResumeTerminatedSessionException on failed session (400)
- InvestigationNotFoundException on unknown run or mismatched case (404)
- REST API POST /api/v1/cases/{case_id}/investigations/{run_id}/resume:
  - Nominal 200 OK for ADMIN, INVESTIGATOR, ANALYST
  - RBAC 403 Forbidden for VIEWER
  - RBAC 403 Forbidden for user outside organization
  - 400 Bad Request CANNOT_RESUME_TERMINATED_SESSION on completed or failed session
  - 404 Not Found on non-existent case or investigation
  - 401 Unauthorized for unauthenticated requests
  - Fallback reconstruction when checkpointer snapshot is not yet written
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.orm import Session

from iryx.auth.models import MembershipRole, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.models import Case
from iryx.cases.services import CaseService
from iryx.core.exceptions import (
    CannotResumeTerminatedSessionException,
    InvestigationNotFoundException,
)
from iryx.core.security import create_access_token
from iryx.main import app
from iryx.orchestrator.checkpointer import (
    get_checkpointer,
    get_memory_saver,
    normalize_postgres_url,
    reset_memory_saver,
)
from iryx.orchestrator.graph import build_investigation_graph
from iryx.orchestrator.models import (
    InvestigationRun,
    InvestigationStatus,
    Phase,
    PhaseName,
    PhaseStatus,
)
from iryx.orchestrator.schemas import H3Decision, H3DecisionRequest
from iryx.orchestrator.services import InvestigationService
from iryx.orchestrator.state import InvestigationState
from iryx.organizations.services import OrganizationService


def auth_header(user: User) -> dict[str, str]:
    """Generate Authorization header with Bearer JWT for specified user."""
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


def sample_plan_dict() -> dict[str, Any]:
    """Return a minimal valid InvestigationPlan dictionary."""
    return {
        "steps": [
            {
                "step_id": 1,
                "tool_name": "log_parser",
                "target_evidence_id": str(uuid.uuid4()),
                "rationale": "Analyse initiale des journaux d'accès",
                "parameters": {"format": "text"},
                "is_blocking": False,
                "continue_on_error": True,
            }
        ],
        "rationale": "Analyse forensique initiale des artefacts système.",
    }


@pytest.fixture(autouse=True)
def clean_checkpointer() -> None:
    """Ensure in-memory checkpointer is cleanly reset before each test."""
    reset_memory_saver()
    yield
    reset_memory_saver()


@pytest.fixture
def test_setup(db_session: Session) -> dict[str, Any]:
    """Create test organization, users with various roles, and an active case."""
    user_svc = UserService(db_session)
    org_svc = OrganizationService(db_session)
    case_svc = CaseService(db_session)

    admin_user = user_svc.create_user(
        UserCreate(email="admin-56@cybersec.fr", password="Password123!")
    )
    investigator_user = user_svc.create_user(
        UserCreate(email="investigator-56@cybersec.fr", password="Password123!")
    )
    analyst_user = user_svc.create_user(
        UserCreate(email="analyst-56@cybersec.fr", password="Password123!")
    )
    viewer_user = user_svc.create_user(
        UserCreate(email="viewer-56@cybersec.fr", password="Password123!")
    )
    outside_user = user_svc.create_user(
        UserCreate(email="stranger-56@other.fr", password="Password123!")
    )

    org = org_svc.create_organization(name="CyberSec Lab 5.6", creator_id=admin_user.id)

    org_svc.add_member(
        org_id=org.id,
        user_id=investigator_user.id,
        role=MembershipRole.INVESTIGATOR,
    )
    org_svc.add_member(
        org_id=org.id,
        user_id=analyst_user.id,
        role=MembershipRole.ANALYST,
    )
    org_svc.add_member(
        org_id=org.id,
        user_id=viewer_user.id,
        role=MembershipRole.VIEWER,
    )

    case = case_svc.create_case(
        org_id=org.id,
        title="Dossier Incident 5.6",
        description="Investigation sur incident de sécurité avec reprise LangGraph",
        creator_id=admin_user.id,
    )

    return {
        "admin": admin_user,
        "investigator": investigator_user,
        "analyst": analyst_user,
        "viewer": viewer_user,
        "outside": outside_user,
        "org": org,
        "case": case,
    }


# ============================================================================
# 1. Checkpointer Factory & Utilities Tests
# ============================================================================


def test_normalize_postgres_url() -> None:
    """Verify URL normalization from SQLAlchemy variants to standard psycopg URLs."""
    assert (
        normalize_postgres_url("postgresql+psycopg://user:pass@localhost:5432/db")
        == "postgresql://user:pass@localhost:5432/db"
    )
    assert (
        normalize_postgres_url("postgresql+psycopg2://user:pass@localhost:5432/db")
        == "postgresql://user:pass@localhost:5432/db"
    )
    assert (
        normalize_postgres_url("postgresql://user:pass@localhost:5432/db")
        == "postgresql://user:pass@localhost:5432/db"
    )


def test_checkpointer_factory_sqlite_and_test_env() -> None:
    """Verify get_checkpointer returns MemorySaver in test and SQLite environments."""
    checkpointer = get_checkpointer(force_memory=True)
    assert isinstance(checkpointer, MemorySaver)

    checkpointer_sqlite = get_checkpointer(database_url="sqlite:///:memory:")
    assert isinstance(checkpointer_sqlite, MemorySaver)


def test_reset_memory_saver() -> None:
    """Verify reset_memory_saver allocates a fresh MemorySaver instance."""
    saver1 = get_memory_saver()
    reset_memory_saver()
    saver2 = get_memory_saver()
    assert saver1 is not saver2


# ============================================================================
# 2. LangGraph State Persistence & Thread Isolation Tests
# ============================================================================


def test_checkpointer_persists_state_and_thread_isolation() -> None:
    """Verify state snapshot is persisted per thread_id without cross-session collision."""
    checkpointer = MemorySaver()
    graph = build_investigation_graph(checkpointer=checkpointer)

    run_a = str(uuid.uuid4())
    run_b = str(uuid.uuid4())
    config_a = {"configurable": {"thread_id": run_a}}
    config_b = {"configurable": {"thread_id": run_b}}

    # Execute session A with pre-set plan
    state_a: InvestigationState = {
        "case_id": "case-a",
        "run_id": run_a,
        "status": "running",
        "plan": sample_plan_dict(),
        "h1_approved": True,
        "iteration_count": 0,
        "error_count": 0,
    }
    graph.invoke(state_a, config=config_a)

    # Execute session B without plan (pauses at planner)
    state_b: InvestigationState = {
        "case_id": "case-b",
        "run_id": run_b,
        "status": "running",
        "iteration_count": 0,
        "error_count": 0,
        "context": {"notification": "En attente de preuves"},
    }
    # Invoke planner with mocked return
    graph.invoke(state_b, config=config_b)

    # Inspect state snapshots
    snapshot_a = graph.get_state(config_a)
    snapshot_b = graph.get_state(config_b)

    assert snapshot_a is not None
    assert snapshot_a.values["case_id"] == "case-a"
    assert snapshot_a.values["run_id"] == run_a
    assert snapshot_a.values["h1_approved"] is True

    assert snapshot_b is not None
    assert snapshot_b.values["case_id"] == "case-b"
    assert snapshot_b.values["run_id"] == run_b
    assert snapshot_b.values.get("h1_approved") is not True


# ============================================================================
# 3. InvestigationService.resume_investigation Unit Tests
# ============================================================================


def test_resume_investigation_nominal_from_paused(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify nominal resume restores state, executes graph, and updates Phase and Run."""
    case: Case = test_setup["case"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.PAUSED,
        current_phase=PhaseName.WAITING_H1,
        validated_plan=sample_plan_dict(),
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.flush()

    initial_phase = Phase(
        id=uuid.uuid4(),
        investigation_run_id=run.id,
        phase_name=PhaseName.WAITING_H1,
        status=PhaseStatus.ACTIVE,
        started_at=now,
    )
    db_session.add(initial_phase)
    db_session.commit()

    checkpointer = MemorySaver()
    service = InvestigationService(db=db_session, checkpointer=checkpointer)

    resumed_run = service.resume_investigation(case_id=case.id, run_id=run.id)
    assert resumed_run.id == run.id
    assert resumed_run.case_id == case.id
    # Since H1 is not approved yet, it remains paused at gate_h1 / waiting_h1
    assert resumed_run.status == InvestigationStatus.PAUSED
    assert resumed_run.current_phase in (PhaseName.GATE_H1, PhaseName.WAITING_H1)


def test_resume_investigation_nominal_with_approved_plan(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify resume on an approved run in executor phase transitions to analyst."""
    case: Case = test_setup["case"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.RUNNING,
        current_phase=PhaseName.EXECUTOR,
        validated_plan=sample_plan_dict(),
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.flush()

    phase_exec = Phase(
        id=uuid.uuid4(),
        investigation_run_id=run.id,
        phase_name=PhaseName.EXECUTOR,
        status=PhaseStatus.ACTIVE,
        started_at=now,
    )
    db_session.add(phase_exec)
    db_session.commit()

    checkpointer = MemorySaver()
    service = InvestigationService(db=db_session, checkpointer=checkpointer)

    resumed_run = service.resume_investigation(case_id=case.id, run_id=run.id)
    assert resumed_run.id == run.id
    # Run executes tools, analyst, verifier and suspends at Gate H2 (waiting_h2)
    # awaiting human review (FR19)
    assert resumed_run.status == InvestigationStatus.PAUSED
    assert resumed_run.current_phase == PhaseName.WAITING_H2


def test_resume_investigation_nominal_from_gate_h3(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify resuming from GATE_H3 without an H3 verdict stays paused at the gate."""
    case: Case = test_setup["case"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.RUNNING,
        current_phase=PhaseName.GATE_H3,
        validated_plan=sample_plan_dict(),
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.flush()

    phase_h3 = Phase(
        id=uuid.uuid4(),
        investigation_run_id=run.id,
        phase_name=PhaseName.GATE_H3,
        status=PhaseStatus.ACTIVE,
        started_at=now,
    )
    db_session.add(phase_h3)
    db_session.commit()

    checkpointer = MemorySaver()
    service = InvestigationService(db=db_session, checkpointer=checkpointer)

    resumed_run = service.resume_investigation(case_id=case.id, run_id=run.id)
    assert resumed_run.id == run.id
    # No H3 decision was recorded in the checkpointer: the barrier must hold.
    assert resumed_run.status == InvestigationStatus.PAUSED
    assert resumed_run.current_phase in (PhaseName.GATE_H3, PhaseName.WAITING_H3)


def test_h3_reject_is_persisted_and_local_report_mode_survives_resume(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """A rejected H3 verdict is stored in the checkpointer and never re-approved on resume."""
    case: Case = test_setup["case"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.PAUSED,
        current_phase=PhaseName.WAITING_H3,
        validated_plan=sample_plan_dict(),
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        Phase(
            id=uuid.uuid4(),
            investigation_run_id=run.id,
            phase_name=PhaseName.GATE_H3,
            status=PhaseStatus.ACTIVE,
            started_at=now,
        )
    )
    db_session.commit()

    checkpointer = MemorySaver()
    service = InvestigationService(db=db_session, checkpointer=checkpointer)
    response = service.arbitrate_gate_h3(
        case_id=case.id,
        run_id=run.id,
        decision_request=H3DecisionRequest(
            decision=H3Decision.REJECT,
            feedback="Gabarit local imposé par le RSSI",
        ),
        user_id=uuid.uuid4(),
    )
    assert response.decision == H3Decision.REJECT

    config = {"configurable": {"thread_id": str(run.id)}}
    graph = build_investigation_graph(checkpointer=checkpointer)
    snapshot = graph.get_state(config)
    assert snapshot.values["h3_approved"] is False
    assert snapshot.values["h3_rejected"] is True
    assert snapshot.values["context"]["local_report_mode"] is True
    assert snapshot.values["context"]["h3_feedback"] == "Gabarit local imposé par le RSSI"

    resumed = service.resume_investigation(case_id=case.id, run_id=run.id)
    assert resumed.status == InvestigationStatus.RUNNING
    assert resumed.current_phase == PhaseName.REPORTING

    final_values = graph.get_state(config).values
    assert final_values.get("h3_approved") is False
    assert final_values.get("h3_rejected") is True
    assert final_values["context"]["local_report_mode"] is True


def test_resume_investigation_terminated_completed_raises_400(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify resuming a COMPLETED session raises CannotResumeTerminatedSessionException (400)."""
    case: Case = test_setup["case"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.COMPLETED,
        current_phase=PhaseName.REPORTING,
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.commit()

    service = InvestigationService(db=db_session, checkpointer=MemorySaver())

    with pytest.raises(CannotResumeTerminatedSessionException) as exc_info:
        service.resume_investigation(case_id=case.id, run_id=run.id)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "CANNOT_RESUME_TERMINATED_SESSION"


def test_resume_investigation_terminated_failed_raises_400(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify resuming a FAILED session raises CannotResumeTerminatedSessionException (400)."""
    case: Case = test_setup["case"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.FAILED,
        current_phase=PhaseName.PLANNER,
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.commit()

    service = InvestigationService(db=db_session, checkpointer=MemorySaver())

    with pytest.raises(CannotResumeTerminatedSessionException) as exc_info:
        service.resume_investigation(case_id=case.id, run_id=run.id)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "CANNOT_RESUME_TERMINATED_SESSION"


def test_resume_investigation_not_found_raises_404(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify resuming an unknown run_id raises InvestigationNotFoundException (404)."""
    case: Case = test_setup["case"]
    service = InvestigationService(db=db_session, checkpointer=MemorySaver())

    with pytest.raises(InvestigationNotFoundException) as exc_info:
        service.resume_investigation(case_id=case.id, run_id=uuid.uuid4())

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "INVESTIGATION_NOT_FOUND"


# ============================================================================
# 4. REST API Endpoint Tests: POST .../investigations/{run_id}/resume
# ============================================================================


def test_api_resume_nominal_analyst_200(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify ANALYST can successfully invoke POST .../resume on a paused session."""
    client = TestClient(app)
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.PAUSED,
        current_phase=PhaseName.WAITING_H1,
        validated_plan=sample_plan_dict(),
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.commit()

    response = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/resume",
        headers=auth_header(analyst),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(run.id)
    assert data["case_id"] == str(case.id)
    assert data["status"] in ("paused", "running", "completed")


def test_api_resume_nominal_investigator_200(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify INVESTIGATOR can successfully invoke POST .../resume."""
    client = TestClient(app)
    case: Case = test_setup["case"]
    investigator: User = test_setup["investigator"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.PAUSED,
        current_phase=PhaseName.WAITING_H1,
        validated_plan=sample_plan_dict(),
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.commit()

    response = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/resume",
        headers=auth_header(investigator),
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(run.id)


def test_api_resume_nominal_admin_200(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify ADMIN can successfully invoke POST .../resume."""
    client = TestClient(app)
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.PAUSED,
        current_phase=PhaseName.WAITING_H1,
        validated_plan=sample_plan_dict(),
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.commit()

    response = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/resume",
        headers=auth_header(admin),
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(run.id)


def test_api_resume_viewer_forbidden_403(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify VIEWER role receives HTTP 403 INSUFFICIENT_PERMISSIONS."""
    client = TestClient(app)
    case: Case = test_setup["case"]
    viewer: User = test_setup["viewer"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.PAUSED,
        current_phase=PhaseName.WAITING_H1,
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.commit()

    response = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/resume",
        headers=auth_header(viewer),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_api_resume_outside_user_forbidden_403(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify user not belonging to organization receives HTTP 403."""
    client = TestClient(app)
    case: Case = test_setup["case"]
    outside: User = test_setup["outside"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.PAUSED,
        current_phase=PhaseName.WAITING_H1,
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.commit()

    response = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/resume",
        headers=auth_header(outside),
    )
    assert response.status_code == 403


def test_api_resume_unauthenticated_401(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify unauthenticated request returns HTTP 401."""
    client = TestClient(app)
    case: Case = test_setup["case"]
    run_id = uuid.uuid4()

    response = client.post(f"/api/v1/cases/{case.id}/investigations/{run_id}/resume")
    assert response.status_code == 401


def test_api_resume_completed_session_returns_400(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify resuming COMPLETED session returns HTTP 400 CANNOT_RESUME_TERMINATED_SESSION."""
    client = TestClient(app)
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.COMPLETED,
        current_phase=PhaseName.REPORTING,
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.commit()

    response = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/resume",
        headers=auth_header(admin),
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "CANNOT_RESUME_TERMINATED_SESSION"
    assert "terminée ou échouée" in body["error"]["message"]


def test_api_resume_failed_session_returns_400(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify resuming FAILED session returns HTTP 400 CANNOT_RESUME_TERMINATED_SESSION."""
    client = TestClient(app)
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]
    now = datetime.now(UTC)

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.FAILED,
        current_phase=PhaseName.PLANNER,
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.commit()

    response = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/resume",
        headers=auth_header(admin),
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "CANNOT_RESUME_TERMINATED_SESSION"


def test_api_resume_unknown_run_returns_404(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify resuming unknown run_id returns HTTP 404 INVESTIGATION_NOT_FOUND."""
    client = TestClient(app)
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]
    unknown_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/cases/{case.id}/investigations/{unknown_id}/resume",
        headers=auth_header(admin),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "INVESTIGATION_NOT_FOUND"


def test_api_resume_unknown_case_returns_404(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify resuming with unknown case_id returns HTTP 404."""
    client = TestClient(app)
    admin: User = test_setup["admin"]
    unknown_case = uuid.uuid4()
    run_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/cases/{unknown_case}/investigations/{run_id}/resume",
        headers=auth_header(admin),
    )
    assert response.status_code == 404
