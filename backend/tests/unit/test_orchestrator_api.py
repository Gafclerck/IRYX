"""Unit tests for Investigation Run API endpoints (/api/v1/cases/{case_id}/investigations).

Validates:
- Nominal 201 Created on start investigation
- Initial Phase created as active with triage
- Anti-concurrency 409 Conflict with INVESTIGATION_ALREADY_RUNNING
- Status PENDING blocks new run (409)
- Status FAILED allows new run (201)
- Status PAUSED blocks new run (409)
- Status COMPLETED allows new run (201)
- Multi-case concurrency allowed (case 1 active does not block case 2)
- Cross-case isolation (run_A retrieved via case_B returns 404 INVESTIGATION_NOT_FOUND)
- Closed case rejects run creation with 422 CASE_CLOSED
- Admin and Analyst roles both allowed (201)
- RBAC 403 Forbidden for viewer role
- RBAC 403 Forbidden for user outside organization
- 404 Not Found for non-existent case
- 200 OK on GET investigation run details
- 200 OK on GET investigation runs list
- 404 Not Found on GET non-existent run
- 401 Unauthorized for unauthenticated requests
"""

import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.api.dependencies import get_db
from iryx.auth.models import MembershipRole, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.models import Case, CaseStatus
from iryx.cases.services import CaseService
from iryx.core.exceptions import ValidationException
from iryx.core.security import create_access_token
from iryx.db.base import Base
from iryx.evidence.models import Evidence
from iryx.main import app
from iryx.orchestrator.models import (
    InvestigationRun,
    InvestigationStatus,
    Phase,
    PhaseName,
    PhaseStatus,
)
from iryx.orchestrator.services import InvestigationService
from iryx.organizations.services import OrganizationService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an in-memory SQLite database session isolated for API testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()

    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provide a TestClient bound to the isolated session."""
    with TestClient(app) as test_client:
        yield test_client


def auth_header(user: User) -> dict[str, str]:
    """Generate Authorization header with Bearer JWT for specified user."""
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_setup(db_session: Session) -> dict[str, object]:
    """Create test organization, users with various roles, and an active case."""
    user_svc = UserService(db_session)
    org_svc = OrganizationService(db_session)
    case_svc = CaseService(db_session)

    # 1. Create Users
    admin_user = user_svc.create_user(
        UserCreate(email="admin@cybersec.fr", password="Password123!")
    )
    investigator_user = user_svc.create_user(
        UserCreate(
            email="investigator@cybersec.fr",
            password="Password123!",
        )
    )
    analyst_user = user_svc.create_user(
        UserCreate(
            email="analyst@cybersec.fr",
            password="Password123!",
        )
    )
    viewer_user = user_svc.create_user(
        UserCreate(email="viewer@cybersec.fr", password="Password123!")
    )
    outside_user = user_svc.create_user(
        UserCreate(email="stranger@other.fr", password="Password123!")
    )

    # 2. Create Organization
    org = org_svc.create_organization(name="CyberSec Lab", creator_id=admin_user.id)

    # 3. Assign Org Memberships
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

    # 4. Create Cases
    case = case_svc.create_case(
        org_id=org.id,
        title="Incident Ransomware Alpha",
        description="Investigation sur attaque ransomware",
        creator_id=investigator_user.id,
    )
    case_2 = case_svc.create_case(
        org_id=org.id,
        title="Incident Exfiltration Beta",
        description="Seconde investigation indépendante",
        creator_id=investigator_user.id,
    )

    return {
        "org": org,
        "case": case,
        "case_2": case_2,
        "admin_user": admin_user,
        "investigator_user": investigator_user,
        "analyst_user": analyst_user,
        "viewer_user": viewer_user,
        "outside_user": outside_user,
        "admin_headers": auth_header(admin_user),
        "investigator_headers": auth_header(investigator_user),
        "analyst_headers": auth_header(analyst_user),
        "viewer_headers": auth_header(viewer_user),
        "outside_headers": auth_header(outside_user),
    }


def test_create_investigation_nominal_success_201(
    client: TestClient, test_setup: dict[str, object]
) -> None:
    """Investigator initiates investigation: returns 201 with running state and active phase."""
    case = test_setup["case"]
    headers = test_setup["investigator_headers"]

    resp = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp.status_code == 201
    data = resp.json()

    assert data["case_id"] == str(case.id)
    assert data["status"] == "running"
    assert data["current_phase"] == "triage"
    assert data["iteration_count"] == 0
    assert data["error_count"] == 0
    assert data["started_at"] is not None
    assert data["updated_at"] is not None

    # Verify initial phase
    assert len(data["phases"]) == 1
    phase = data["phases"][0]
    assert phase["phase_name"] == "triage"
    assert phase["status"] == "active"
    assert phase["started_at"] is not None


def test_create_investigation_by_admin_and_analyst_201(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """BH-8: Admin and Analyst roles are both authorized to initiate an investigation."""
    case = test_setup["case"]
    case_2 = test_setup["case_2"]
    admin_headers = test_setup["admin_headers"]
    analyst_headers = test_setup["analyst_headers"]

    # Admin initiates on case 1
    resp_admin = client.post(f"/api/v1/cases/{case.id}/investigations", headers=admin_headers)
    assert resp_admin.status_code == 201

    # Analyst initiates on case 2
    resp_analyst = client.post(
        f"/api/v1/cases/{case_2.id}/investigations", headers=analyst_headers
    )
    assert resp_analyst.status_code == 201


def test_create_investigation_concurrency_conflict_409(
    client: TestClient, test_setup: dict[str, object]
) -> None:
    """Concurrent investigation creation on active case returns 409 conflict code."""
    case = test_setup["case"]
    headers = test_setup["investigator_headers"]

    # First run succeeds
    resp1 = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp1.status_code == 201

    # Second concurrent run fails with 409 Conflict
    resp2 = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp2.status_code == 409
    data = resp2.json()
    assert data["error"]["code"] == "INVESTIGATION_ALREADY_RUNNING"


def test_create_investigation_concurrency_conflict_when_pending_and_paused_409(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """VG-4: Status PENDING and PAUSED both block starting a new run with 409."""
    case = test_setup["case"]
    headers = test_setup["investigator_headers"]

    # 1. Start run and set to PENDING
    resp1 = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp1.status_code == 201
    run_id = resp1.json()["id"]

    run = db_session.get(InvestigationRun, uuid.UUID(run_id))
    assert run is not None
    run.status = InvestigationStatus.PENDING
    db_session.commit()

    # Attempt second run while previous is PENDING -> 409
    resp_pending = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp_pending.status_code == 409
    assert resp_pending.json()["error"]["code"] == "INVESTIGATION_ALREADY_RUNNING"

    # 2. Transition run status to PAUSED -> still blocks with 409
    run.status = InvestigationStatus.PAUSED
    db_session.commit()

    resp_paused = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp_paused.status_code == 409
    assert resp_paused.json()["error"]["code"] == "INVESTIGATION_ALREADY_RUNNING"


def test_create_investigation_allowed_after_completion_or_failure(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """VG-4: Status COMPLETED and FAILED both allow launching a new investigation run."""
    case = test_setup["case"]
    headers = test_setup["investigator_headers"]

    # 1. Start run and transition to COMPLETED
    resp1 = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp1.status_code == 201
    run_id = resp1.json()["id"]

    run = db_session.get(InvestigationRun, uuid.UUID(run_id))
    assert run is not None
    run.status = InvestigationStatus.COMPLETED
    db_session.commit()

    # Next run succeeds
    resp2 = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp2.status_code == 201
    run_id_2 = resp2.json()["id"]

    # 2. Transition second run to FAILED
    run_2 = db_session.get(InvestigationRun, uuid.UUID(run_id_2))
    assert run_2 is not None
    run_2.status = InvestigationStatus.FAILED
    db_session.commit()

    # Third run succeeds after previous failed
    resp3 = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp3.status_code == 201


def test_multi_case_concurrent_investigations_allowed(
    client: TestClient, test_setup: dict[str, object]
) -> None:
    """VG-2: An active investigation on case_1 does not prevent starting a run on case_2."""
    case_1 = test_setup["case"]
    case_2 = test_setup["case_2"]
    headers = test_setup["investigator_headers"]

    # Start run on case 1
    resp1 = client.post(f"/api/v1/cases/{case_1.id}/investigations", headers=headers)
    assert resp1.status_code == 201
    assert resp1.json()["case_id"] == str(case_1.id)

    # Start run on case 2 simultaneously succeeds
    resp2 = client.post(f"/api/v1/cases/{case_2.id}/investigations", headers=headers)
    assert resp2.status_code == 201
    assert resp2.json()["case_id"] == str(case_2.id)


def test_cross_case_investigation_isolation_404(
    client: TestClient, test_setup: dict[str, object]
) -> None:
    """VG-1 / BH-9: Retrieving run_A via case_B returns 404 INVESTIGATION_NOT_FOUND."""
    case_1 = test_setup["case"]
    case_2 = test_setup["case_2"]
    headers = test_setup["investigator_headers"]

    # Create run on case 1
    create_resp = client.post(f"/api/v1/cases/{case_1.id}/investigations", headers=headers)
    assert create_resp.status_code == 201
    run_id_1 = create_resp.json()["id"]

    # Attempt to retrieve run_1 under case 2
    cross_resp = client.get(
        f"/api/v1/cases/{case_2.id}/investigations/{run_id_1}", headers=headers
    )
    assert cross_resp.status_code == 404
    assert cross_resp.json()["error"]["code"] == "INVESTIGATION_NOT_FOUND"


def test_create_investigation_closed_case_validation_error_422(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """BH-14: Starting an investigation on a closed case raises 422 CASE_CLOSED."""
    case = test_setup["case"]
    headers = test_setup["investigator_headers"]

    # Mark case as closed
    case_entity = db_session.get(Case, case.id)
    assert case_entity is not None
    case_entity.status = CaseStatus.CLOSED
    db_session.commit()

    resp = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CASE_CLOSED"


def test_create_investigation_viewer_forbidden_403(
    client: TestClient, test_setup: dict[str, object]
) -> None:
    """Viewer role is forbidden from starting an investigation (403)."""
    case = test_setup["case"]
    headers = test_setup["viewer_headers"]

    resp = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_create_investigation_outside_org_forbidden_403(
    client: TestClient, test_setup: dict[str, object]
) -> None:
    """User not member of the case's organization is forbidden (403)."""
    case = test_setup["case"]
    headers = test_setup["outside_headers"]

    resp = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp.status_code == 403


def test_create_investigation_case_not_found_404(
    client: TestClient, test_setup: dict[str, object]
) -> None:
    """Non-existent case ID returns 404 CASE_NOT_FOUND."""
    headers = test_setup["investigator_headers"]
    random_case_id = uuid.uuid4()

    resp = client.post(f"/api/v1/cases/{random_case_id}/investigations", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_get_investigation_run_details_200(
    client: TestClient, test_setup: dict[str, object]
) -> None:
    """Retrieve details of an existing investigation run (200 OK)."""
    case = test_setup["case"]
    inv_headers = test_setup["investigator_headers"]
    viewer_headers = test_setup["viewer_headers"]

    # Start run
    create_resp = client.post(f"/api/v1/cases/{case.id}/investigations", headers=inv_headers)
    assert create_resp.status_code == 201
    run_id = create_resp.json()["id"]

    # Viewer can consult investigation run
    get_resp = client.get(
        f"/api/v1/cases/{case.id}/investigations/{run_id}", headers=viewer_headers
    )
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == run_id
    assert data["case_id"] == str(case.id)
    assert data["status"] == "running"
    assert data["current_phase"] == "triage"
    assert len(data["phases"]) == 1
    assert data["phases"][0]["phase_name"] == "triage"
    assert data["phases"][0]["status"] == "active"


def test_list_investigation_runs_200(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """BH-6: GET /api/v1/cases/{case_id}/investigations returns all runs for the case."""
    case = test_setup["case"]
    headers = test_setup["investigator_headers"]

    # Initial list is empty
    resp_empty = client.get(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp_empty.status_code == 200
    assert resp_empty.json() == []

    # Create run 1, mark completed
    resp1 = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp1.status_code == 201
    run_id_1 = resp1.json()["id"]

    run_1 = db_session.get(InvestigationRun, uuid.UUID(run_id_1))
    assert run_1 is not None
    run_1.status = InvestigationStatus.COMPLETED
    db_session.commit()

    # Create run 2
    resp2 = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp2.status_code == 201

    # List runs now returns 2
    resp_list = client.get(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp_list.status_code == 200
    runs = resp_list.json()
    assert len(runs) == 2
    run_ids = [r["id"] for r in runs]
    assert run_id_1 in run_ids


def test_get_investigation_run_not_found_404(
    client: TestClient, test_setup: dict[str, object]
) -> None:
    """Retrieving a non-existent run ID returns 404 INVESTIGATION_NOT_FOUND."""
    case = test_setup["case"]
    headers = test_setup["investigator_headers"]
    random_run_id = uuid.uuid4()

    resp = client.get(
        f"/api/v1/cases/{case.id}/investigations/{random_run_id}", headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INVESTIGATION_NOT_FOUND"


def test_unauthenticated_request_401(
    client: TestClient, test_setup: dict[str, object]
) -> None:
    """Unauthenticated requests return 401 UNAUTHORIZED."""
    case = test_setup["case"]

    resp_post = client.post(f"/api/v1/cases/{case.id}/investigations")
    assert resp_post.status_code == 401

    resp_get = client.get(f"/api/v1/cases/{case.id}/investigations/{uuid.uuid4()}")
    assert resp_get.status_code == 401

    resp_list = client.get(f"/api/v1/cases/{case.id}/investigations")
    assert resp_list.status_code == 401


def _setup_paused_h1_run(
    db_session: Session,
    case_id: uuid.UUID,
    with_plan: bool = True,
    evidence_id: uuid.UUID | None = None,
) -> tuple[InvestigationRun, Evidence | None]:
    """Helper creating an investigation run paused at Gate H1 with an optional plan."""
    now = datetime.now(UTC)
    evidence: Evidence | None = None
    if evidence_id is None:
        evidence = Evidence(
            id=uuid.uuid4(),
            case_id=case_id,
            original_name="Security.evtx",
            file_size=2048,
            sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            detected_type="application/x-ms-evtx",
        )
        db_session.add(evidence)
        db_session.commit()
        target_evidence_id = evidence.id
    else:
        target_evidence_id = evidence_id

    plan_data = None
    if with_plan:
        plan_data = {
            "summary": "Plan forensique pour analyse des logs",
            "steps": [
                {
                    "step_id": 1,
                    "tool_name": "parse_evtx",
                    "target_evidence_id": str(target_evidence_id),
                    "parameters": {},
                    "rationale": "Analyse des connexions suspectes",
                }
            ],
        }

    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case_id,
        status=InvestigationStatus.PAUSED,
        current_phase=PhaseName.WAITING_H1,
        validated_plan=plan_data,
        iteration_count=0,
        error_count=0,
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.flush()

    phase = Phase(
        id=uuid.uuid4(),
        investigation_run_id=run.id,
        phase_name=PhaseName.GATE_H1,
        status=PhaseStatus.ACTIVE,
        started_at=now,
    )
    db_session.add(phase)
    db_session.commit()
    return run, evidence


def test_get_investigation_plan_nominal_200(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Consultation nominale du plan (HTTP 200 OK avec InvestigationPlan)."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, evidence = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.get(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/plan", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "Plan forensique pour analyse des logs"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["tool_name"] == "parse_evtx"
    assert data["steps"][0]["target_evidence_id"] == str(evidence.id)


def test_get_investigation_plan_not_found_404(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Consultation plan inexistant (HTTP 404 PLAN_NOT_FOUND)."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=False)

    resp = client.get(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/plan", headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PLAN_NOT_FOUND"


def test_get_investigation_plan_viewer_allowed_200(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Viewer can read the investigation plan via verify_case_access."""
    case = test_setup["case"]
    headers = test_setup["viewer_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.get(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/plan", headers=headers
    )
    assert resp.status_code == 200


def test_get_investigation_plan_unauthenticated_401(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Unauthenticated request to GET plan returns 401 UNAUTHORIZED."""
    case = test_setup["case"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.get(f"/api/v1/cases/{case.id}/investigations/{run.id}/plan")
    assert resp.status_code == 401


def test_arbitrate_h1_approve_nominal_200(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Approbation nominale H1: HTTP 200 OK, status: running, current_phase: executor."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "approve"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["current_phase"] == "executor"
    assert data["decision"] == "approve"
    assert "approuvé" in data["message"].lower()

    # Verify DB persistence
    refreshed_run = db_session.get(InvestigationRun, run.id)
    assert refreshed_run.status == InvestigationStatus.RUNNING
    assert refreshed_run.current_phase == PhaseName.EXECUTOR

    # Verify phase lifecycle
    phases = refreshed_run.phases
    assert len(phases) == 2
    gate_phase = phases[0]
    executor_phase = phases[1]
    assert gate_phase.phase_name == PhaseName.GATE_H1
    assert gate_phase.status == PhaseStatus.COMPLETED
    assert gate_phase.completed_at is not None
    assert executor_phase.phase_name == PhaseName.EXECUTOR
    assert executor_phase.status == PhaseStatus.ACTIVE


def test_arbitrate_h1_approve_admin_allowed_200(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Admin role is authorized to approve Gate H1."""
    case = test_setup["case"]
    headers = test_setup["admin_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "approve"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_arbitrate_h1_approve_investigator_allowed_200(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Investigator role is authorized to approve Gate H1."""
    case = test_setup["case"]
    headers = test_setup["investigator_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "approve"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_arbitrate_h1_modify_nominal_200(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Modification nominale H1 avec modified_plan valide: HTTP 200, transition executor."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, evidence = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    modified_plan = {
        "summary": "Plan modifié par l'analyste avec étape supplémentaire",
        "steps": [
            {
                "step_id": 1,
                "tool_name": "parse_evtx",
                "target_evidence_id": str(evidence.id),
                "parameters": {"filter": "EventID=4624"},
                "rationale": "Filtrage sur les connexions réussies",
            }
        ],
    }

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "modify", "modified_plan": modified_plan},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["current_phase"] == "executor"
    assert data["decision"] == "modify"
    assert data["validated_plan"]["summary"] == modified_plan["summary"]
    assert len(data["validated_plan"]["steps"]) == 1

    # Verify DB persistence
    refreshed_run = db_session.get(InvestigationRun, run.id)
    assert refreshed_run.validated_plan["summary"] == modified_plan["summary"]
    assert refreshed_run.status == InvestigationStatus.RUNNING
    assert refreshed_run.current_phase == PhaseName.EXECUTOR


def test_arbitrate_h1_modify_missing_modified_plan_422(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Modification sans modified_plan: HTTP 422 MISSING_MODIFIED_PLAN."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "modify"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "MISSING_MODIFIED_PLAN"


def test_arbitrate_h1_modify_invalid_steps_count_422(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Modification avec modified_plan ayant plus de 10 étapes: HTTP 422 INVALID_PLAN."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, evidence = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    # 11 steps (> 10)
    steps = [
        {
            "step_id": i + 1,
            "tool_name": "parse_evtx",
            "target_evidence_id": str(evidence.id),
            "parameters": {},
            "rationale": f"Etape {i + 1}",
        }
        for i in range(11)
    ]
    bad_plan = {"summary": "Plan avec trop d'étapes", "steps": steps}

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "modify", "modified_plan": bad_plan},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_PLAN"


def test_arbitrate_h1_modify_unknown_tool_422(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Modification avec modified_plan ayant un outil non whitelisté: HTTP 422 INVALID_PLAN."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, evidence = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    bad_plan = {
        "summary": "Plan avec outil non autorisé",
        "steps": [
            {
                "step_id": 1,
                "tool_name": "arbitrary_shell_command",
                "target_evidence_id": str(evidence.id),
                "parameters": {},
                "rationale": "Execution de commande arbitraire",
            }
        ],
    }

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "modify", "modified_plan": bad_plan},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_PLAN"


def test_arbitrate_h1_modify_evidence_not_in_case_422(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Modification ciblant une preuve n'appartenant pas au dossier: HTTP 422 INVALID_PLAN."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    foreign_evidence_id = uuid.uuid4()
    bad_plan = {
        "summary": "Plan ciblant une preuve étrangère",
        "steps": [
            {
                "step_id": 1,
                "tool_name": "parse_evtx",
                "target_evidence_id": str(foreign_evidence_id),
                "parameters": {},
                "rationale": "Analyse d'une preuve d'un autre dossier",
            }
        ],
    }

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "modify", "modified_plan": bad_plan},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_PLAN"


def test_arbitrate_h1_reject_nominal_stop_200(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Rejet nominal sans replanification (return_to_planner=False): HTTP 200, status: completed."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "reject", "return_to_planner": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["decision"] == "reject"

    refreshed_run = db_session.get(InvestigationRun, run.id)
    assert refreshed_run.status == InvestigationStatus.COMPLETED


def test_arbitrate_h1_reject_with_return_to_planner_200(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Rejet avec replanification: HTTP 200, status: running, current_phase: planner."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={
            "decision": "reject",
            "return_to_planner": True,
            "feedback": "Périmètre incomplet : ajouter analyse de mémoire vive.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["current_phase"] == "planner"
    assert data["decision"] == "reject"

    refreshed_run = db_session.get(InvestigationRun, run.id)
    assert refreshed_run.status == InvestigationStatus.RUNNING
    assert refreshed_run.current_phase == PhaseName.PLANNER
    assert refreshed_run.iteration_count == 1


def test_arbitrate_h1_invalid_gate_state_running_422(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Arbitrage sur session non en pause H1 (status: running): HTTP 422 INVALID_GATE_STATE."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]

    # Start a nominal investigation (status: running, current_phase: triage)
    resp_start = client.post(f"/api/v1/cases/{case.id}/investigations", headers=headers)
    assert resp_start.status_code == 201
    run_id = resp_start.json()["id"]

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run_id}/gates/h1",
        headers=headers,
        json={"decision": "approve"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_GATE_STATE"


def test_arbitrate_h1_invalid_gate_state_completed_422(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Arbitrage sur session déjà terminée (status: completed): HTTP 422 INVALID_GATE_STATE."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    # Mark run completed
    run.status = InvestigationStatus.COMPLETED
    db_session.commit()

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "approve"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_GATE_STATE"


def test_arbitrate_h1_viewer_forbidden_403(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Viewer attempting to submit Gate H1 arbitration: HTTP 403 Forbidden."""
    case = test_setup["case"]
    headers = test_setup["viewer_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "approve"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] in ("FORBIDDEN", "INSUFFICIENT_PERMISSIONS")


def test_arbitrate_h1_outside_user_forbidden_403(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """User outside case organization attempting Gate H1 arbitration: HTTP 403 Forbidden."""
    case = test_setup["case"]
    headers = test_setup["outside_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "approve"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] in ("FORBIDDEN", "INSUFFICIENT_PERMISSIONS")


def test_arbitrate_h1_cross_case_isolation_404(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Run belonging to Case 1 arbitrated via Case 2 path returns 404 INVESTIGATION_NOT_FOUND."""
    case = test_setup["case"]
    case_2 = test_setup["case_2"]
    headers = test_setup["analyst_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.post(
        f"/api/v1/cases/{case_2.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "approve"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INVESTIGATION_NOT_FOUND"


def test_arbitrate_h1_unauthenticated_401(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Unauthenticated request to Gate H1 arbitration returns 401 UNAUTHORIZED."""
    case = test_setup["case"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        json={"decision": "approve"},
    )
    assert resp.status_code == 401


def test_pause_at_gate_h1_service_lifecycle(
    test_setup: dict[str, object], db_session: Session
) -> None:
    """pause_at_gate_h1 pauses running session, closes active phase, and activates gate_h1."""
    case = test_setup["case"]
    service = InvestigationService(db_session)
    run = service.start_investigation(case.id)
    assert run.status == InvestigationStatus.RUNNING
    assert run.current_phase == PhaseName.TRIAGE

    paused_run = service.pause_at_gate_h1(case.id, run.id)
    assert paused_run.status == InvestigationStatus.PAUSED
    assert paused_run.current_phase == PhaseName.WAITING_H1

    # Active phase must now be gate_h1
    active_phase = [p for p in paused_run.phases if p.status == PhaseStatus.ACTIVE]
    assert len(active_phase) == 1
    assert active_phase[0].phase_name == PhaseName.GATE_H1

    # Attempting to pause a completed run raises ValidationException
    paused_run.status = InvestigationStatus.COMPLETED
    db_session.commit()
    with pytest.raises(ValidationException) as exc_info:
        service.pause_at_gate_h1(case.id, paused_run.id)
    assert exc_info.value.code == "INVALID_STATUS_TRANSITION"


def test_arbitrate_h1_approve_no_plan_404(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Approbation d'un run pausé à H1 sans plan associé retourne 404 PLAN_NOT_FOUND."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=False)

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "approve"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "PLAN_NOT_FOUND"


def test_get_investigation_plan_cross_case_isolation_404(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """GET plan sur un mauvais dossier retourne 404 INVESTIGATION_NOT_FOUND."""
    case = test_setup["case"]
    case_2 = test_setup["case_2"]
    headers = test_setup["analyst_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.get(
        f"/api/v1/cases/{case_2.id}/investigations/{run.id}/plan",
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "INVESTIGATION_NOT_FOUND"


def test_get_investigation_plan_outside_user_forbidden_403(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """GET plan par un utilisateur externe à l'organisation retourne 403 Forbidden."""
    case = test_setup["case"]
    headers = test_setup["outside_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    resp = client.get(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/plan",
        headers=headers,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] in ("FORBIDDEN", "INSUFFICIENT_PERMISSIONS")


def test_arbitrate_h1_replan_max_iteration_bound_422(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Replanification rejetée avec 422 MAX_ITERATIONS_REACHED si iteration_count >= 5."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    run.iteration_count = 5
    db_session.commit()

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "reject", "return_to_planner": True},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "MAX_ITERATIONS_REACHED"


def test_arbitrate_h1_modify_evidence_without_sha256_422(
    client: TestClient, test_setup: dict[str, object], db_session: Session
) -> None:
    """Modification ciblant une preuve non scellée (sha256 vide/nul) retourne 422 INVALID_PLAN."""
    case = test_setup["case"]
    headers = test_setup["analyst_headers"]
    run, _ = _setup_paused_h1_run(db_session, case.id, with_plan=True)

    unsealed_evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case.id,
        original_name="unsealed.raw",
        file_size=1024,
        sha256=None,
        detected_type="raw",
    )
    db_session.add(unsealed_evidence)
    db_session.commit()

    modified_plan = {
        "summary": "Plan ciblant une preuve non scellée",
        "steps": [
            {
                "step_id": 1,
                "tool_name": "parse_evtx",
                "target_evidence_id": str(unsealed_evidence.id),
                "parameters": {},
                "rationale": "Test preuve non scellée",
            }
        ],
    }

    resp = client.post(
        f"/api/v1/cases/{case.id}/investigations/{run.id}/gates/h1",
        headers=headers,
        json={"decision": "modify", "modified_plan": modified_plan},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_PLAN"


