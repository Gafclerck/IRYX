"""API Integration tests for Forensic Gateway consultation endpoints (/api/v1/cases/{case_id}/...).

Tests:
- GET /api/v1/cases/{case_id}/tool-executions (pagination, filters, 422, 403, 404)
- GET /api/v1/cases/{case_id}/tool-executions/{execution_id} (details, 404)
- GET /api/v1/cases/{case_id}/observations (pagination, filters, 422, 403, 404)
- GET /api/v1/cases/{case_id}/observations/{observation_id} (details, 404)
- GET /api/v1/gateway/tools (registered tools catalog)
"""

import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.analytics.models import Observation
from iryx.api.dependencies import get_db
from iryx.auth.models import MembershipRole, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.models import Case
from iryx.cases.services import CaseService
from iryx.core.security import create_access_token
from iryx.db.base import Base
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.main import app
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


@pytest.fixture
def test_setup(db_session: Session) -> dict[str, object]:
    """Create test organization, users, and an active case."""
    user_svc = UserService(db_session)
    org_svc = OrganizationService(db_session)
    case_svc = CaseService(db_session)

    admin = user_svc.create_user(UserCreate(email="admin@soc.iryx", password="Password123!"))
    analyst = user_svc.create_user(UserCreate(email="analyst@soc.iryx", password="Password123!"))
    viewer = user_svc.create_user(UserCreate(email="viewer@soc.iryx", password="Password123!"))
    outsider = user_svc.create_user(
        UserCreate(email="outsider@external.iryx", password="Password123!")
    )

    org = org_svc.create_organization(name="CERT Interne", creator_id=admin.id)
    org_svc.add_member(org_id=org.id, user_id=analyst.id, role=MembershipRole.ANALYST)
    org_svc.add_member(org_id=org.id, user_id=viewer.id, role=MembershipRole.VIEWER)

    # Secondary organization for tenant isolation tests
    other_admin = user_svc.create_user(
        UserCreate(email="other@external.iryx", password="Password123!")
    )
    other_org = org_svc.create_organization(name="CERT Externe", creator_id=other_admin.id)

    case = case_svc.create_case(
        org_id=org.id,
        title="Dossier Incident Ransomware",
        creator_id=admin.id,
        description="Investigation active",
    )

    other_case = case_svc.create_case(
        org_id=other_org.id,
        title="Dossier Externe Isolé",
        creator_id=other_admin.id,
        description="Dossier externe isolé pour tests multi-tenant.",
    )

    return {
        "org": org,
        "other_org": other_org,
        "admin": admin,
        "analyst": analyst,
        "viewer": viewer,
        "outsider": outsider,
        "other_admin": other_admin,
        "case": case,
        "other_case": other_case,
    }


def auth_header(user: User) -> dict[str, str]:
    """Generate Authorization header with Bearer JWT for specified user."""
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# 1. GET /api/v1/cases/{case_id}/tool-executions (Pagination & Filters)
# =========================================================================


def test_list_tool_executions_empty_nominal(client: TestClient, test_setup: dict) -> None:
    """Verify empty tool execution list returns valid pagination structure."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    response = client.get(
        f"/api/v1/cases/{case.id}/tool-executions",
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["total_items"] == 0
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert data["has_more"] is False


def test_list_tool_executions_paginated(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify pagination limit and offset across multiple tool execution records."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    # Seed 60 tool executions
    for i in range(60):
        db_session.add(
            ToolExecution(
                case_id=case.id,
                tool_name="parse_evtx" if i % 2 == 0 else "parse_text_logs",
                tool_version="1.0.0",
                agent_role="Executor",
                parameters={"index": i},
                result_sha256="a" * 64,
                duration_ms=100 + i,
                status=ToolExecutionStatus.SUCCESS,
            )
        )
    db_session.commit()

    # Page 1: 20 items
    res1 = client.get(
        f"/api/v1/cases/{case.id}/tool-executions?limit=20&offset=0",
        headers=auth_header(analyst),
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert len(data1["items"]) == 20
    assert data1["total"] == 60
    assert data1["total_items"] == 60
    assert data1["limit"] == 20
    assert data1["offset"] == 0
    assert data1["has_more"] is True

    # Page 3: offset 40, 20 items
    res3 = client.get(
        f"/api/v1/cases/{case.id}/tool-executions?limit=20&offset=40",
        headers=auth_header(analyst),
    )
    assert res3.status_code == 200
    data3 = res3.json()
    assert len(data3["items"]) == 20
    assert data3["has_more"] is False


def test_list_tool_executions_filtering(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify filtering tool executions by tool_name and status."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    db_session.add(
        ToolExecution(
            case_id=case.id,
            tool_name="parse_evtx",
            tool_version="1.0.0",
            agent_role="Executor",
            parameters={},
            result_sha256="1" * 64,
            duration_ms=50,
            status=ToolExecutionStatus.SUCCESS,
        )
    )
    db_session.add(
        ToolExecution(
            case_id=case.id,
            tool_name="parse_text_logs",
            tool_version="1.0.0",
            agent_role="Executor",
            parameters={},
            result_sha256=None,
            duration_ms=50,
            status=ToolExecutionStatus.ERROR,
            error_message="Invalid log format",
        )
    )
    db_session.commit()

    # Filter by tool_name
    res_tool = client.get(
        f"/api/v1/cases/{case.id}/tool-executions?tool_name=parse_evtx",
        headers=auth_header(analyst),
    )
    assert res_tool.status_code == 200
    data_tool = res_tool.json()
    assert data_tool["total"] == 1
    assert data_tool["items"][0]["tool_name"] == "parse_evtx"

    # Filter by status
    res_status = client.get(
        f"/api/v1/cases/{case.id}/tool-executions?status=error",
        headers=auth_header(analyst),
    )
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["total"] == 1
    assert data_status["items"][0]["status"] == "error"

    # Filter by date range (start_date, end_date)
    now = datetime.now(UTC)
    start_str = (now - timedelta(hours=1)).isoformat()
    end_str = (now + timedelta(hours=1)).isoformat()
    res_date = client.get(
        f"/api/v1/cases/{case.id}/tool-executions",
        params={"start_date": start_str, "end_date": end_str},
        headers=auth_header(analyst),
    )
    assert res_date.status_code == 200
    data_date = res_date.json()
    assert data_date["total"] == 2

    # Date range in the future matching 0 executions
    future_start = (now + timedelta(days=1)).isoformat()
    future_end = (now + timedelta(days=2)).isoformat()
    res_future = client.get(
        f"/api/v1/cases/{case.id}/tool-executions",
        params={"start_date": future_start, "end_date": future_end},
        headers=auth_header(analyst),
    )
    assert res_future.status_code == 200
    assert res_future.json()["total"] == 0


def test_get_tool_execution_by_id(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify single tool execution retrieval and 404 isolation."""
    case: Case = test_setup["case"]
    other_case: Case = test_setup["other_case"]
    analyst: User = test_setup["analyst"]

    execution = ToolExecution(
        case_id=case.id,
        tool_name="hash_sha256",
        tool_version="1.0.0",
        agent_role="Executor",
        parameters={"evidence_id": str(uuid.uuid4())},
        result_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        duration_ms=12,
        status=ToolExecutionStatus.SUCCESS,
    )
    db_session.add(execution)
    db_session.commit()

    # Success
    res = client.get(
        f"/api/v1/cases/{case.id}/tool-executions/{execution.id}",
        headers=auth_header(analyst),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(execution.id)
    assert data["tool_name"] == "hash_sha256"
    assert data["result_sha256"] == execution.result_sha256

    # 404 for unknown execution
    res_404 = client.get(
        f"/api/v1/cases/{case.id}/tool-executions/{uuid.uuid4()}",
        headers=auth_header(analyst),
    )
    assert res_404.status_code == 404

    # 404 when querying from another case
    other_admin: User = test_setup["other_admin"]
    res_cross = client.get(
        f"/api/v1/cases/{other_case.id}/tool-executions/{execution.id}",
        headers=auth_header(other_admin),
    )
    assert res_cross.status_code == 404


# =========================================================================
# 2. GET /api/v1/cases/{case_id}/observations (Pagination & Filters)
# =========================================================================


def test_list_observations_paginated(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify pagination across observation records."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    for i in range(55):
        db_session.add(
            Observation(
                case_id=case.id,
                tool_name="parse_evtx",
                normalized_content={"event_id": 4624, "idx": i},
                timestamp_utc=datetime.now(UTC),
                source_location=f"C:\\Windows\\System32\\winevt\\Logs\\Security.evtx:{i}",
            )
        )
    db_session.commit()

    res = client.get(
        f"/api/v1/cases/{case.id}/observations?limit=50&offset=0",
        headers=auth_header(analyst),
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 50
    assert data["total"] == 55
    assert data["total_items"] == 55
    assert data["has_more"] is True


def test_list_observations_filters(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify filtering observations by tool_name and source_id."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    evidence_id = uuid.uuid4()

    db_session.add(
        Observation(
            case_id=case.id,
            source_id=evidence_id,
            tool_name="parse_text_logs",
            normalized_content={"record": "auth failure"},
            timestamp_utc=datetime.now(UTC),
        )
    )
    db_session.add(
        Observation(
            case_id=case.id,
            tool_name="parse_registry",
            normalized_content={"hive": "SYSTEM"},
            timestamp_utc=datetime.now(UTC),
        )
    )
    db_session.commit()

    # Filter tool_name
    res_tool = client.get(
        f"/api/v1/cases/{case.id}/observations?tool_name=parse_text_logs",
        headers=auth_header(analyst),
    )
    assert res_tool.status_code == 200
    data_tool = res_tool.json()
    assert data_tool["total"] == 1
    assert data_tool["items"][0]["tool_name"] == "parse_text_logs"

    # Filter source_id
    res_source = client.get(
        f"/api/v1/cases/{case.id}/observations?source_id={evidence_id}",
        headers=auth_header(analyst),
    )
    assert res_source.status_code == 200
    data_source = res_source.json()
    assert data_source["total"] == 1
    assert data_source["items"][0]["source_id"] == str(evidence_id)

    # Filter tool_execution_id
    exec_id = uuid.uuid4()
    db_session.add(
        Observation(
            case_id=case.id,
            tool_name="parse_evtx",
            tool_execution_id=exec_id,
            normalized_content={"event": 4624},
            timestamp_utc=datetime.now(UTC),
        )
    )
    db_session.commit()

    res_exec = client.get(
        f"/api/v1/cases/{case.id}/observations?tool_execution_id={exec_id}",
        headers=auth_header(analyst),
    )
    assert res_exec.status_code == 200
    data_exec = res_exec.json()
    assert data_exec["total"] == 1
    assert data_exec["items"][0]["tool_execution_id"] == str(exec_id)

    # Filter date range (start_date, end_date)
    now = datetime.now(UTC)
    start_str = (now - timedelta(hours=1)).isoformat()
    end_str = (now + timedelta(hours=1)).isoformat()
    res_date = client.get(
        f"/api/v1/cases/{case.id}/observations",
        params={"start_date": start_str, "end_date": end_str},
        headers=auth_header(analyst),
    )
    assert res_date.status_code == 200
    assert res_date.json()["total"] >= 1


def test_get_observation_by_id(client: TestClient, test_setup: dict, db_session: Session) -> None:
    """Verify single observation retrieval and 404 isolation."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    obs = Observation(
        case_id=case.id,
        tool_name="parse_execution",
        normalized_content={"executable": "cmd.exe", "run_count": 5},
        source_location="C:\\Windows\\Prefetch\\CMD.EXE-12345678.pf",
    )
    db_session.add(obs)
    db_session.commit()

    # Success
    res = client.get(
        f"/api/v1/cases/{case.id}/observations/{obs.id}",
        headers=auth_header(analyst),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == str(obs.id)
    assert data["tool_name"] == "parse_execution"
    assert data["normalized_content"]["executable"] == "cmd.exe"

    # 404 for unknown observation
    res_404 = client.get(
        f"/api/v1/cases/{case.id}/observations/{uuid.uuid4()}",
        headers=auth_header(analyst),
    )
    assert res_404.status_code == 404

    # 404 when querying an observation from another case
    other_case: Case = test_setup["other_case"]
    other_admin: User = test_setup["other_admin"]
    res_cross = client.get(
        f"/api/v1/cases/{other_case.id}/observations/{obs.id}",
        headers=auth_header(other_admin),
    )
    assert res_cross.status_code == 404


# =========================================================================
# 3. Validation Errors (422) & RBAC Access Control (401, 403, 404)
# =========================================================================


def test_invalid_pagination_parameters_returns_422(client: TestClient, test_setup: dict) -> None:
    """Verify limit > 100, limit < 1, or offset < 0 return HTTP 422."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    # Limit = 150 (exceeds max 100)
    res_high = client.get(
        f"/api/v1/cases/{case.id}/tool-executions?limit=150",
        headers=auth_header(analyst),
    )
    assert res_high.status_code == 422

    # Limit = 0 (below min 1)
    res_low = client.get(
        f"/api/v1/cases/{case.id}/tool-executions?limit=0",
        headers=auth_header(analyst),
    )
    assert res_low.status_code == 422

    # Offset = -1
    res_neg = client.get(
        f"/api/v1/cases/{case.id}/observations?offset=-1",
        headers=auth_header(analyst),
    )
    assert res_neg.status_code == 422


def test_invalid_date_format_returns_422(client: TestClient, test_setup: dict) -> None:
    """Verify non-ISO datetime formats return standardized HTTP 422."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    res = client.get(
        f"/api/v1/cases/{case.id}/tool-executions?start_date=not-a-date",
        headers=auth_header(analyst),
    )
    assert res.status_code == 422


def test_invalid_status_returns_422(client: TestClient, test_setup: dict) -> None:
    """Verify invalid status query parameter returns HTTP 422."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    res = client.get(
        f"/api/v1/cases/{case.id}/tool-executions?status=invalid_status",
        headers=auth_header(analyst),
    )
    assert res.status_code == 422


def test_start_date_greater_than_end_date_returns_422(client: TestClient, test_setup: dict) -> None:
    """Verify start_date > end_date returns HTTP 422 on tool-executions and observations."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    # tool-executions
    res_exec = client.get(
        f"/api/v1/cases/{case.id}/tool-executions?start_date=2026-11-25T12:00:00Z&end_date=2026-11-20T12:00:00Z",
        headers=auth_header(analyst),
    )
    assert res_exec.status_code == 422

    # observations
    res_obs = client.get(
        f"/api/v1/cases/{case.id}/observations?start_date=2026-11-25T12:00:00Z&end_date=2026-11-20T12:00:00Z",
        headers=auth_header(analyst),
    )
    assert res_obs.status_code == 422


def test_security_rbac_case_access_control(client: TestClient, test_setup: dict) -> None:
    """Verify verify_case_access enforces 401, 403, and 404 boundaries."""
    case: Case = test_setup["case"]
    outsider: User = test_setup["outsider"]
    other_admin: User = test_setup["other_admin"]

    # 401 Unauthenticated
    res_401 = client.get(f"/api/v1/cases/{case.id}/tool-executions")
    assert res_401.status_code == 401

    # 403 Forbidden for non-member
    res_403 = client.get(
        f"/api/v1/cases/{case.id}/tool-executions",
        headers=auth_header(outsider),
    )
    assert res_403.status_code == 403

    # 403 Forbidden for user from another organization
    res_tenant = client.get(
        f"/api/v1/cases/{case.id}/observations",
        headers=auth_header(other_admin),
    )
    assert res_tenant.status_code == 403

    # 404 Not Found for non-existent case
    random_case_id = uuid.uuid4()
    res_404 = client.get(
        f"/api/v1/cases/{random_case_id}/tool-executions",
        headers=auth_header(outsider),
    )
    assert res_404.status_code == 404


def test_list_registered_tools_catalog(client: TestClient, test_setup: dict) -> None:
    """Verify GET /api/v1/gateway/tools returns metadata of registered tools."""
    analyst: User = test_setup["analyst"]

    res = client.get(
        "/api/v1/gateway/tools",
        headers=auth_header(analyst),
    )
    assert res.status_code == 200
    tools = res.json()
    assert isinstance(tools, list)
    assert len(tools) >= 5
    tool_names = [t["name"] for t in tools]
    assert "parse_evtx" in tool_names
    assert "parse_text_logs" in tool_names
    assert "parse_registry" in tool_names
    assert "parse_execution" in tool_names
    assert "analyze_memory" in tool_names
