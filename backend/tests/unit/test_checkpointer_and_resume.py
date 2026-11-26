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

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import select
from sqlalchemy.orm import Session

from iryx.ai.schemas import LLMRole
from iryx.analytics.models import Finding, FindingSeverity, FindingStatus
from iryx.auth.models import MembershipRole, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.models import Case
from iryx.cases.services import CaseService
from iryx.core.exceptions import (
    CannotResumeTerminatedSessionException,
    InvestigationNotFoundException,
    ReportGenerationFailedException,
)
from iryx.core.security import create_access_token
from iryx.main import app
from iryx.orchestrator.checkpointer import (
    get_checkpointer,
    get_checkpointer_dependency,
    get_memory_saver,
    normalize_postgres_url,
    reset_memory_saver,
)
from iryx.orchestrator.graph import build_investigation_graph, get_runtime_context
from iryx.orchestrator.models import (
    InvestigationRun,
    InvestigationStatus,
    Phase,
    PhaseName,
    PhaseStatus,
)
from iryx.orchestrator.schemas import (
    AnonymizedPreviewOut,
    H3Decision,
    H3DecisionRequest,
    InvestigationRunOut,
)
from iryx.orchestrator.services import InvestigationService, set_runtime_context
from iryx.orchestrator.state import InvestigationState
from iryx.organizations.services import OrganizationService
from iryx.reporting.models import Report
from iryx.reporting.pseudonymizer import DeterministicPseudonymizer
from iryx.reporting.schemas import CANONICAL_SECTION_KEYS


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


# ============================================================================
# Story 8.3 — H3 pseudonym continuity across preview, arbitration and resume
# ============================================================================


class _RecordingRapporteurClient:
    """LLM double recording the approved external drafting prompt."""

    def __init__(self) -> None:
        self.role = "rapporteur"
        self.calls: list[list[dict[str, Any]]] = []
        self.response = json.dumps(
            {key: "Texte factuel." for key in CANONICAL_SECTION_KEYS}, ensure_ascii=False
        )

    def for_role(self, role: Any) -> "_RecordingRapporteurClient":
        """Record the requested role and return this client."""
        self.requested_role = role
        return self

    async def complete(self, messages: list[dict[str, Any]], temperature: float = 0.0) -> dict:
        """Capture the external prompt."""
        self.calls.append(messages)
        return {"content": self.response}


def _h3_run(db_session: Session, case: Case, phase: PhaseName) -> InvestigationRun:
    """Create a paused investigation run ready for H3 arbitration."""
    now = datetime.now(UTC)
    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.PAUSED,
        current_phase=phase,
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
    return run


def test_preview_token_is_restored_and_reused_after_approved_resume(
    db_session: Session,
    test_setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the H3 preview pseudonym survives arbitration and resume unchanged."""
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]
    db_session.add(
        Finding(
            case_id=case.id,
            title="Connexion suspecte depuis 198.51.100.27",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.VALIDATED,
        )
    )
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    checkpointer = MemorySaver()
    service = InvestigationService(db=db_session, checkpointer=checkpointer)
    config = {"configurable": {"thread_id": str(run.id)}}

    preview = service.get_anonymized_preview(case.id, run.id, user_id=admin.id)
    assert preview.has_entities
    pseudonym = re.search(r"IP_INTERNAL_\d+", preview.anonymized_text)
    assert pseudonym is not None

    seeded = build_investigation_graph(checkpointer=checkpointer).get_state(config).values
    assert seeded["current_phase"] == "gate_h3"
    assert seeded["status"] == "running"
    assert "h1_approved" not in seeded
    assert "h2_approved" not in seeded
    assert seeded["context"]["pseudonymization_case_id"] == str(case.id)

    service.arbitrate_gate_h3(
        case_id=case.id,
        run_id=run.id,
        decision_request=H3DecisionRequest(
            decision=H3Decision.APPROVE,
            feedback="Rédaction externe autorisée",
        ),
        user_id=admin.id,
    )
    approved_state = build_investigation_graph(checkpointer=checkpointer).get_state(config).values
    assert approved_state["h3_approved"] is True
    assert "local_report_mode" not in approved_state["context"]

    client = _RecordingRapporteurClient()
    requested_roles: list[LLMRole] = []

    def _factory(role: LLMRole) -> _RecordingRapporteurClient:
        requested_roles.append(role)
        return client

    monkeypatch.setattr("iryx.orchestrator.graph.get_llm_client", _factory)
    set_runtime_context({})
    try:
        resumed = service.resume_investigation(
            case_id=case.id,
            run_id=run.id,
            user_id=admin.id,
        )
    finally:
        set_runtime_context({})

    assert requested_roles == [LLMRole.RAPPORTEUR]
    assert resumed.current_phase == PhaseName.REPORTING
    assert len(client.calls) == 1
    assert pseudonym.group(0) in client.calls[0][1]["content"]
    reports = list(
        db_session.scalars(select(Report).where(Report.case_id == case.id))
    )
    assert len(reports) == 2
    assert all(pseudonym.group(0) in report.content for report in reports)


def test_corrupt_token_is_ignored_when_resume_never_reaches_reporting(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify a stale corrupt token does not block a resume that stops before reporting."""
    case: Case = test_setup["case"]
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    checkpointer = MemorySaver()
    graph = build_investigation_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": str(run.id)}}
    graph.update_state(
        config,
        {
            "context": {
                "pseudonymization_token": "corrupted-token",
                "pseudonymization_case_id": str(case.id),
            }
        },
    )

    service = InvestigationService(db=db_session, checkpointer=checkpointer)
    resumed = service.resume_investigation(case_id=case.id, run_id=run.id)

    assert resumed.id == run.id
    assert resumed.current_phase in (PhaseName.GATE_H3, PhaseName.WAITING_H3)


def test_corrupt_token_fails_typed_when_resume_reaches_reporting(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify a corrupt token aborts an approved reporting resume with the typed error."""
    case: Case = test_setup["case"]
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    checkpointer = MemorySaver()
    graph = build_investigation_graph(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": str(run.id)}}
    graph.update_state(
        config,
        {
            "h3_approved": True,
            "current_phase": "gate_h3",
            "context": {
                "pseudonymization_token": "corrupted-token",
                "pseudonymization_case_id": str(case.id),
            },
        },
    )

    service = InvestigationService(db=db_session, checkpointer=checkpointer)
    with pytest.raises(ReportGenerationFailedException):
        service.resume_investigation(case_id=case.id, run_id=run.id)
    assert (
        list(db_session.scalars(select(Report).where(Report.case_id == case.id))) == []
    )


def test_failed_checkpointer_token_write_aborts_resume_without_report(
    db_session: Session,
    test_setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a failed pseudonym-token checkpoint write raises the typed error."""
    case: Case = test_setup["case"]
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    pseudonymizer = DeterministicPseudonymizer()
    pseudonymizer.pseudonymize("Connexion 198.51.100.27", case_id=str(case.id))
    token = pseudonymizer.export_token(case.id)

    class _FailingGraph:
        def get_state(self, config: dict[str, Any]) -> SimpleNamespace:
            return SimpleNamespace(
                values={
                    "current_phase": "gate_h3",
                    "h3_approved": True,
                    "context": {
                        "pseudonymization_token": token,
                        "pseudonymization_case_id": str(case.id),
                    },
                }
            )

        def update_state(self, config: dict[str, Any], update: dict[str, Any]) -> None:
            raise RuntimeError("checkpointer indisponible")

    monkeypatch.setattr(
        "iryx.orchestrator.services.build_investigation_graph",
        lambda checkpointer=None: _FailingGraph(),
    )

    service = InvestigationService(db=db_session, checkpointer=MemorySaver())
    with pytest.raises(ReportGenerationFailedException, match="checkpointer"):
        service.resume_investigation(case_id=case.id, run_id=run.id)
    assert (
        list(db_session.scalars(select(Report).where(Report.case_id == case.id))) == []
    )


def test_pseudonym_token_from_another_case_is_rejected(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify a token bound to another case cannot be restored for this case."""
    case: Case = test_setup["case"]
    foreign_case_id = uuid.uuid4()
    foreign = DeterministicPseudonymizer()
    foreign.pseudonymize("Connexion externe", case_id=str(foreign_case_id))
    token = foreign.export_token(foreign_case_id)

    service = InvestigationService(db=db_session, checkpointer=MemorySaver())
    with pytest.raises(ReportGenerationFailedException, match="pseudonymisation"):
        service._restore_report_pseudonymizer(
            case.id, {"pseudonymization_token": token}
        )


def test_reject_then_approve_clears_local_report_mode(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify a later approval removes the local flag left by a rejection."""
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    service = InvestigationService(db=db_session, checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": str(run.id)}}
    graph = build_investigation_graph(checkpointer=service.checkpointer)

    service.arbitrate_gate_h3(
        case_id=case.id,
        run_id=run.id,
        decision_request=H3DecisionRequest(decision=H3Decision.REJECT),
        user_id=admin.id,
    )
    rejected = graph.get_state(config).values
    assert rejected["context"]["local_report_mode"] is True

    run.status = InvestigationStatus.PAUSED
    run.current_phase = PhaseName.WAITING_H3
    db_session.commit()
    service.arbitrate_gate_h3(
        case_id=case.id,
        run_id=run.id,
        decision_request=H3DecisionRequest(decision=H3Decision.APPROVE),
        user_id=admin.id,
    )
    approved = graph.get_state(config).values
    assert approved["h3_approved"] is True
    assert "local_report_mode" not in approved["context"]


def test_compiled_resume_propagates_typed_generation_failure(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify the compiled graph/resume path surfaces a typed drafting failure."""
    case: Case = test_setup["case"]
    db_session.add(
        Finding(
            case_id=case.id,
            title="Connexion suspecte depuis 198.51.100.27",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.VALIDATED,
        )
    )
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    pseudonymizer = DeterministicPseudonymizer()
    pseudonymizer.pseudonymize("Connexion 198.51.100.27", case_id=str(case.id))
    token = pseudonymizer.export_token(case.id)
    checkpointer = MemorySaver()
    graph = build_investigation_graph(checkpointer=checkpointer)
    graph.update_state(
        {"configurable": {"thread_id": str(run.id)}},
        {
            "case_id": str(case.id),
            "run_id": str(run.id),
            "h3_approved": True,
            "current_phase": "gate_h3",
            "context": {
                "pseudonymization_token": token,
                "pseudonymization_case_id": str(case.id),
            },
        },
    )

    service = InvestigationService(db=db_session, checkpointer=checkpointer)
    with pytest.raises(ReportGenerationFailedException) as exc_info:
        service.resume_investigation(case_id=case.id, run_id=run.id)
    assert exc_info.value.code == "REPORT_GENERATION_FAILED"
    assert exc_info.value.status_code == 500
    assert (
        list(db_session.scalars(select(Report).where(Report.case_id == case.id))) == []
    )


def test_approved_resume_resolves_rapporteur_client_from_factory(
    db_session: Session,
    test_setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify approved production drafting needs no manually injected LLM client."""
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]
    db_session.add(
        Finding(
            case_id=case.id,
            title="Connexion suspecte depuis 198.51.100.27",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.VALIDATED,
        )
    )
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    checkpointer = MemorySaver()
    service = InvestigationService(db=db_session, checkpointer=checkpointer)

    service.get_anonymized_preview(case.id, run.id, user_id=admin.id)
    service.arbitrate_gate_h3(
        case_id=case.id,
        run_id=run.id,
        decision_request=H3DecisionRequest(decision=H3Decision.APPROVE),
        user_id=admin.id,
    )

    client = _RecordingRapporteurClient()
    requested_roles: list[LLMRole] = []

    def _factory(role: LLMRole) -> _RecordingRapporteurClient:
        requested_roles.append(role)
        return client

    monkeypatch.setattr("iryx.orchestrator.graph.get_llm_client", _factory)
    set_runtime_context({})
    try:
        resumed = service.resume_investigation(case_id=case.id, run_id=run.id, user_id=admin.id)
    finally:
        set_runtime_context({})

    assert requested_roles == [LLMRole.RAPPORTEUR]
    assert resumed.current_phase == PhaseName.REPORTING
    assert len(client.calls) == 1
    reports = list(db_session.scalars(select(Report).where(Report.case_id == case.id)))
    assert len(reports) == 2
    assert all(
        report.sha256 == hashlib.sha256(report.content.encode("utf-8")).hexdigest()
        for report in reports
    )


def test_approved_pseudonym_token_cannot_be_replaced(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify a stored approved token is immutable, while identical writes remain valid."""
    case: Case = test_setup["case"]
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    service = InvestigationService(db=db_session, checkpointer=MemorySaver())

    service._persist_pseudonymizer_token(case.id, run.id, "token-approuve")
    service._persist_pseudonymizer_token(case.id, run.id, "token-approuve")

    with pytest.raises(ReportGenerationFailedException, match="remplacé"):
        service._persist_pseudonymizer_token(case.id, run.id, "token-different")


def test_inject_runtime_drops_stale_llm_client_unless_explicit() -> None:
    """Verify a per-request LLM client never leaks into a later runtime context."""
    stale = object()
    explicit = object()
    set_runtime_context({"llm_client": stale, "user_id": uuid.uuid4()})
    try:
        InvestigationService._inject_runtime(db="db-marker")
        assert "llm_client" not in get_runtime_context()
        InvestigationService._inject_runtime(llm_client=explicit)
        assert get_runtime_context()["llm_client"] is explicit
    finally:
        set_runtime_context({})


def test_router_forwards_current_user_to_preview_and_resume(
    db_session: Session,
    test_setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify both H3 HTTP endpoints pass the authenticated user id to the service."""
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    seen: dict[str, Any] = {}

    def _preview(self: Any, case_id: Any, run_id: Any, *, user_id: Any = None) -> Any:
        seen["preview"] = user_id
        return AnonymizedPreviewOut(
            run_id=run_id,
            case_id=case_id,
            anonymized_text="Aucune entité",
            entity_count=0,
            has_entities=False,
        )

    def _resume(self: Any, case_id: Any, run_id: Any, user_id: Any = None) -> Any:
        seen["resume"] = user_id
        return InvestigationRunOut.model_validate(
            self.get_investigation_run(case_id=case_id, run_id=run_id)
        )

    monkeypatch.setattr(InvestigationService, "get_anonymized_preview", _preview)
    monkeypatch.setattr(InvestigationService, "resume_investigation", _resume)

    client = TestClient(app)
    headers = auth_header(admin)
    preview_response = client.get(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/anonymized-preview",
        headers=headers,
    )
    resume_response = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/resume",
        headers=headers,
    )
    assert preview_response.status_code == 200
    assert resume_response.status_code == 200
    assert seen == {"preview": admin.id, "resume": admin.id}


def test_approved_resume_over_http_uses_authenticated_identity(
    db_session: Session,
    test_setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify an HTTP resume ignores a differing checkpoint identity."""
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]
    outsider: User = test_setup["outside"]
    db_session.add(
        Finding(
            case_id=case.id,
            title="Connexion suspecte depuis 198.51.100.27",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.VALIDATED,
        )
    )
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    checkpointer = MemorySaver()
    service = InvestigationService(db=db_session, checkpointer=checkpointer)
    service.get_anonymized_preview(case.id, run.id, user_id=admin.id)

    config = {"configurable": {"thread_id": str(run.id)}}
    graph = build_investigation_graph(checkpointer=checkpointer)
    token = graph.get_state(config).values["context"]["pseudonymization_token"]
    graph.update_state(
        config,
        {
            "h3_approved": True,
            "current_phase": "gate_h3",
            "context": {
                "pseudonymization_token": token,
                "pseudonymization_case_id": str(case.id),
                "user_id": str(outsider.id),
            },
        },
    )

    client = _RecordingRapporteurClient()
    monkeypatch.setattr("iryx.orchestrator.graph.get_llm_client", lambda role: client)
    app.dependency_overrides[get_checkpointer_dependency] = lambda: checkpointer
    set_runtime_context({})
    try:
        response = TestClient(app).post(
            f"/api/v1/cases/{case.id}/investigations/{run.id}/resume",
            headers=auth_header(admin),
        )
    finally:
        app.dependency_overrides.pop(get_checkpointer_dependency, None)
        set_runtime_context({})

    assert response.status_code == 200, response.text
    assert len(client.calls) == 1
    reports = list(db_session.scalars(select(Report).where(Report.case_id == case.id)))
    assert len(reports) == 2


def test_divergent_runtime_preview_token_fails_without_mutating_store(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify an approved checkpoint token cannot be replaced by a shared store."""
    case: Case = test_setup["case"]
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    checkpointer = MemorySaver()

    approved = DeterministicPseudonymizer()
    approved.pseudonymize("Connexion 198.51.100.27", case_id=str(case.id))
    approved_token = approved.export_token(case.id)
    graph = build_investigation_graph(checkpointer=checkpointer)
    graph.update_state(
        {"configurable": {"thread_id": str(run.id)}},
        {
            "context": {
                "pseudonymization_token": approved_token,
                "pseudonymization_case_id": str(case.id),
            }
        },
    )

    shared = DeterministicPseudonymizer()
    shared.pseudonymize("Connexion 203.0.113.9", case_id=str(case.id))
    shared_token = shared.export_token(case.id)
    set_runtime_context({"pseudonymizer": shared})
    try:
        with pytest.raises(ReportGenerationFailedException, match="remplacé"):
            InvestigationService(db=db_session, checkpointer=checkpointer).get_anonymized_preview(
                case.id, run.id
            )
    finally:
        set_runtime_context({})
    assert shared.export_token(case.id) == shared_token


def test_pseudonym_token_bound_to_another_case_is_rejected(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify a stored token cannot be reused under a different case identity."""
    case: Case = test_setup["case"]
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    checkpointer = MemorySaver()
    service = InvestigationService(db=db_session, checkpointer=checkpointer)
    service._persist_pseudonymizer_token(case.id, run.id, "token-approuve")

    config = {"configurable": {"thread_id": str(run.id)}}
    graph = build_investigation_graph(checkpointer=checkpointer)
    context = dict(graph.get_state(config).values["context"])
    context["pseudonymization_case_id"] = str(uuid.uuid4())
    graph.update_state(config, {"context": context})

    with pytest.raises(ReportGenerationFailedException, match="autre dossier"):
        service._persist_pseudonymizer_token(case.id, run.id, "token-approuve")


def test_runtime_preview_without_store_restores_approved_token(
    db_session: Session,
    test_setup: dict[str, Any],
) -> None:
    """Verify an injected pseudonymizer restores the checkpoint table before drafting."""
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]
    db_session.add(
        Finding(
            case_id=case.id,
            title="Connexion 198.51.100.27",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.VALIDATED,
        )
    )
    run = _h3_run(db_session, case, PhaseName.WAITING_H3)
    checkpointer = MemorySaver()

    approved = DeterministicPseudonymizer()
    approved.pseudonymize("Connexion 198.51.100.27", case_id=str(case.id))
    stored_token = approved.export_token(case.id)
    graph = build_investigation_graph(checkpointer=checkpointer)
    graph.update_state(
        {"configurable": {"thread_id": str(run.id)}},
        {
            "context": {
                "pseudonymization_token": stored_token,
                "pseudonymization_case_id": str(case.id),
            }
        },
    )

    injected = DeterministicPseudonymizer()
    assert InvestigationService._current_case_token(injected, case.id) is None
    set_runtime_context({"pseudonymizer": injected})
    try:
        preview = InvestigationService(
            db=db_session, checkpointer=checkpointer
        ).get_anonymized_preview(case.id, run.id, user_id=admin.id)
    finally:
        set_runtime_context({})
    assert "198.51.100.27" not in preview.anonymized_text
    assert injected.export_token(case.id) == stored_token
