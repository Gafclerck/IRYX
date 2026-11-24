"""Integration tests for Investigation Cases API endpoints (/api/v1/cases)."""

import time
import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.api.dependencies import get_db
from iryx.auth.models import Membership, MembershipRole, Organization, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.core.security import create_access_token
from iryx.db.base import Base
from iryx.main import app
from iryx.organizations.services import OrganizationService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an in-memory SQLite database session isolated for integration testing."""
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
    """Create test organization and users with distinct RBAC roles."""
    user_svc = UserService(db_session)
    org_svc = OrganizationService(db_session)

    admin = user_svc.create_user(UserCreate(email="admin@soc.iryx", password="Password123!"))
    investigator = user_svc.create_user(
        UserCreate(email="investigator@soc.iryx", password="Password123!")
    )
    analyst = user_svc.create_user(UserCreate(email="analyst@soc.iryx", password="Password123!"))
    viewer = user_svc.create_user(UserCreate(email="viewer@soc.iryx", password="Password123!"))
    outsider = user_svc.create_user(UserCreate(email="outsider@soc.iryx", password="Password123!"))

    # Create Organization with admin as creator
    org = org_svc.create_organization(name="CERT Interne", creator_id=admin.id)

    # Add other members
    org_svc.add_member(org_id=org.id, user_id=investigator.id, role=MembershipRole.INVESTIGATOR)
    org_svc.add_member(org_id=org.id, user_id=analyst.id, role=MembershipRole.ANALYST)
    org_svc.add_member(org_id=org.id, user_id=viewer.id, role=MembershipRole.VIEWER)

    # Second organization for multi-tenant isolation testing
    other_admin = user_svc.create_user(
        UserCreate(email="other_admin@external.iryx", password="Password123!")
    )
    other_org = org_svc.create_organization(name="CERT Externe", creator_id=other_admin.id)

    return {
        "org": org,
        "other_org": other_org,
        "admin": admin,
        "investigator": investigator,
        "analyst": analyst,
        "viewer": viewer,
        "outsider": outsider,
        "other_admin": other_admin,
    }


def auth_header(user: User) -> dict[str, str]:
    """Generate Authorization header with Bearer JWT for specified user."""
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# 1. POST /api/v1/organizations/{org_id}/cases (Create Case)
# =========================================================================


def test_create_case_nominal_by_operational_roles(client: TestClient, test_setup: dict) -> None:
    """Verify nominal case creation by admin, investigator, and analyst returns HTTP 201."""
    org: Organization = test_setup["org"]

    for role_name in ["admin", "investigator", "analyst"]:
        user: User = test_setup[role_name]
        response = client.post(
            f"/api/v1/organizations/{org.id}/cases",
            json={"title": f"Incident par {role_name}", "description": "Investigation active."},
            headers=auth_header(user),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == f"Incident par {role_name}"
        assert data["description"] == "Investigation active."
        assert data["status"] == "open"
        assert data["organization_id"] == str(org.id)
        assert data["created_by"] == str(user.id)
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data


def test_create_case_by_viewer_forbidden(client: TestClient, test_setup: dict) -> None:
    """Verify creation by viewer role returns HTTP 403 INSUFFICIENT_PERMISSIONS."""
    org: Organization = test_setup["org"]
    viewer: User = test_setup["viewer"]

    response = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Tentative par viewer", "description": "Ne doit pas passer."},
        headers=auth_header(viewer),
    )

    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_create_case_by_outsider_forbidden(client: TestClient, test_setup: dict) -> None:
    """Verify creation by non-member user returns HTTP 403 INSUFFICIENT_PERMISSIONS."""
    org: Organization = test_setup["org"]
    outsider: User = test_setup["outsider"]

    response = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Tentative par outsider"},
        headers=auth_header(outsider),
    )

    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_create_case_unauthenticated(client: TestClient, test_setup: dict) -> None:
    """Verify creation without JWT returns HTTP 401 UNAUTHORIZED."""
    org: Organization = test_setup["org"]
    response = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Sans auth"},
    )
    assert response.status_code == 401


def test_create_case_invalid_title_returns_422(client: TestClient, test_setup: dict) -> None:
    """Verify empty or overly long title returns HTTP 422 VALIDATION_ERROR."""
    org: Organization = test_setup["org"]
    admin: User = test_setup["admin"]

    # 1. Whitespace title
    res_empty = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "   "},
        headers=auth_header(admin),
    )
    assert res_empty.status_code == 422
    assert res_empty.json()["error"]["code"] == "VALIDATION_ERROR"

    # 2. Too long title (> 255 chars)
    res_long = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "X" * 256},
        headers=auth_header(admin),
    )
    assert res_long.status_code == 422
    assert res_long.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_case_unknown_organization_returns_404(client: TestClient, test_setup: dict) -> None:
    """Verify creation with unknown org_id returns HTTP 404 ORGANIZATION_NOT_FOUND."""
    admin: User = test_setup["admin"]
    fake_org_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/organizations/{fake_org_id}/cases",
        json={"title": "Dossier Orphelin"},
        headers=auth_header(admin),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORGANIZATION_NOT_FOUND"


# =========================================================================
# 2. GET /api/v1/organizations/{org_id}/cases (List Cases)
# =========================================================================


def test_list_cases_nominal_and_pagination(client: TestClient, test_setup: dict) -> None:
    """Verify list_cases returns paginated CaseListResponse for members including viewer."""
    org: Organization = test_setup["org"]
    other_org: Organization = test_setup["other_org"]
    admin: User = test_setup["admin"]
    other_admin: User = test_setup["other_admin"]
    viewer: User = test_setup["viewer"]

    # Create 1 case in other_org to verify tenant isolation in case listing
    client.post(
        f"/api/v1/organizations/{other_org.id}/cases",
        json={"title": "Dossier Autre Org"},
        headers=auth_header(other_admin),
    )

    # Create 3 cases in org
    for i in range(3):
        time.sleep(0.005)
        client.post(
            f"/api/v1/organizations/{org.id}/cases",
            json={"title": f"Dossier {i + 1}"},
            headers=auth_header(admin),
        )

    # Viewer queries list with limit=2, offset=0
    response = client.get(
        f"/api/v1/organizations/{org.id}/cases?limit=2&offset=0",
        headers=auth_header(viewer),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert data["has_more"] is True

    # 1. Multi-tenant isolation: verify all returned cases belong strictly to org
    assert all(item["organization_id"] == str(org.id) for item in data["items"])

    # 2. Reverse chronological order: Dossier 3 first, then Dossier 2
    assert data["items"][0]["title"] == "Dossier 3"
    assert data["items"][1]["title"] == "Dossier 2"

    # Page 2: limit=2, offset=2 -> Dossier 1 last
    res_p2 = client.get(
        f"/api/v1/organizations/{org.id}/cases?limit=2&offset=2",
        headers=auth_header(viewer),
    )
    assert res_p2.status_code == 200
    data_p2 = res_p2.json()
    assert len(data_p2["items"]) == 1
    assert data_p2["items"][0]["title"] == "Dossier 1"
    assert data_p2["items"][0]["organization_id"] == str(org.id)
    assert data_p2["has_more"] is False


def test_list_cases_by_outsider_forbidden(client: TestClient, test_setup: dict) -> None:
    """Verify list_cases by outsider returns HTTP 403 INSUFFICIENT_PERMISSIONS."""
    org: Organization = test_setup["org"]
    outsider: User = test_setup["outsider"]

    response = client.get(
        f"/api/v1/organizations/{org.id}/cases",
        headers=auth_header(outsider),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_list_cases_unknown_organization(client: TestClient, test_setup: dict) -> None:
    """Verify list_cases with unknown org_id returns HTTP 404 ORGANIZATION_NOT_FOUND."""
    admin: User = test_setup["admin"]
    fake_org_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/organizations/{fake_org_id}/cases",
        headers=auth_header(admin),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORGANIZATION_NOT_FOUND"


# =========================================================================
# 3. GET /api/v1/cases/{case_id} (Retrieve Case by ID)
# =========================================================================


def test_get_case_nominal(client: TestClient, test_setup: dict) -> None:
    """Verify get_case returns HTTP 200 with CaseOut for member (including viewer)."""
    org: Organization = test_setup["org"]
    admin: User = test_setup["admin"]
    viewer: User = test_setup["viewer"]

    create_res = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Dossier Consultation", "description": "Détails requis."},
        headers=auth_header(admin),
    )
    case_id = create_res.json()["id"]

    # Retrieve by viewer
    get_res = client.get(
        f"/api/v1/cases/{case_id}",
        headers=auth_header(viewer),
    )
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["id"] == case_id
    assert data["title"] == "Dossier Consultation"
    assert data["status"] == "open"


def test_get_case_by_outsider_forbidden(client: TestClient, test_setup: dict) -> None:
    """Verify get_case by member of another org returns HTTP 403 INSUFFICIENT_PERMISSIONS."""
    org: Organization = test_setup["org"]
    admin: User = test_setup["admin"]
    other_admin: User = test_setup["other_admin"]

    create_res = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Dossier Restreint"},
        headers=auth_header(admin),
    )
    case_id = create_res.json()["id"]

    response = client.get(
        f"/api/v1/cases/{case_id}",
        headers=auth_header(other_admin),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_get_case_unknown_id(client: TestClient, test_setup: dict) -> None:
    """Verify get_case with unknown ID returns HTTP 404 CASE_NOT_FOUND."""
    admin: User = test_setup["admin"]
    fake_case_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/cases/{fake_case_id}",
        headers=auth_header(admin),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


# =========================================================================
# 4. PATCH /api/v1/cases/{case_id}/status (Status Transitions)
# =========================================================================


def test_patch_case_status_nominal_lifecycle(client: TestClient, test_setup: dict) -> None:
    """Verify nominal sequence: open -> in_progress -> review -> closed."""
    org: Organization = test_setup["org"]
    investigator: User = test_setup["investigator"]

    create_res = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Dossier Cycle Nominal"},
        headers=auth_header(investigator),
    )
    case_id = create_res.json()["id"]

    # 1. open -> in_progress
    r1 = client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "in_progress"},
        headers=auth_header(investigator),
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "in_progress"

    # 2. in_progress -> review
    r2 = client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "review"},
        headers=auth_header(investigator),
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "review"

    # 3. review -> closed
    r3 = client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "closed"},
        headers=auth_header(investigator),
    )
    assert r3.status_code == 200
    assert r3.json()["status"] == "closed"


def test_patch_case_status_allowed_backward_transitions(
    client: TestClient, test_setup: dict
) -> None:
    """Verify allowed backward transitions: in_progress -> open and review -> in_progress."""
    org: Organization = test_setup["org"]
    investigator: User = test_setup["investigator"]

    create_res = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Dossier Transitions Arrière"},
        headers=auth_header(investigator),
    )
    case_id = create_res.json()["id"]

    # 1. open -> in_progress
    client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "in_progress"},
        headers=auth_header(investigator),
    )

    # 2. Backward: in_progress -> open
    r_back_open = client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "open"},
        headers=auth_header(investigator),
    )
    assert r_back_open.status_code == 200
    assert r_back_open.json()["status"] == "open"

    # 3. open -> in_progress -> review
    client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "in_progress"},
        headers=auth_header(investigator),
    )
    client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "review"},
        headers=auth_header(investigator),
    )

    # 4. Backward: review -> in_progress
    r_back_in_prog = client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "in_progress"},
        headers=auth_header(investigator),
    )
    assert r_back_in_prog.status_code == 200
    assert r_back_in_prog.json()["status"] == "in_progress"


def test_patch_case_status_illegal_from_closed(client: TestClient, test_setup: dict) -> None:
    """Verify transition from closed status returns HTTP 400 INVALID_STATUS_TRANSITION."""
    org: Organization = test_setup["org"]
    admin: User = test_setup["admin"]

    create_res = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Dossier Clôturé"},
        headers=auth_header(admin),
    )
    case_id = create_res.json()["id"]

    # Direct close: open -> closed
    r_close = client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "closed"},
        headers=auth_header(admin),
    )
    assert r_close.status_code == 200
    assert r_close.json()["status"] == "closed"

    # Attempt illegal transition: closed -> in_progress
    r_illegal = client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "in_progress"},
        headers=auth_header(admin),
    )
    assert r_illegal.status_code == 400
    data = r_illegal.json()
    assert data["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_patch_case_status_illegal_open_to_review(client: TestClient, test_setup: dict) -> None:
    """Verify illegal transition open -> review returns HTTP 400 INVALID_STATUS_TRANSITION."""
    org: Organization = test_setup["org"]
    admin: User = test_setup["admin"]

    create_res = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Dossier Nouveau"},
        headers=auth_header(admin),
    )
    case_id = create_res.json()["id"]

    response = client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "review"},
        headers=auth_header(admin),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_patch_case_status_by_viewer_forbidden(client: TestClient, test_setup: dict) -> None:
    """Verify viewer cannot update case status (HTTP 403 INSUFFICIENT_PERMISSIONS)."""
    org: Organization = test_setup["org"]
    admin: User = test_setup["admin"]
    viewer: User = test_setup["viewer"]

    create_res = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Dossier pour Test Viewer"},
        headers=auth_header(admin),
    )
    case_id = create_res.json()["id"]

    response = client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "in_progress"},
        headers=auth_header(viewer),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_patch_case_status_by_outsider_forbidden(client: TestClient, test_setup: dict) -> None:
    """Verify non-member user cannot update case status (HTTP 403 INSUFFICIENT_PERMISSIONS)."""
    org: Organization = test_setup["org"]
    admin: User = test_setup["admin"]
    outsider: User = test_setup["outsider"]

    create_res = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Dossier pour Test Outsider"},
        headers=auth_header(admin),
    )
    case_id = create_res.json()["id"]

    response = client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "in_progress"},
        headers=auth_header(outsider),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_patch_case_status_unknown_case(client: TestClient, test_setup: dict) -> None:
    """Verify patch status on non-existent case returns HTTP 404 CASE_NOT_FOUND."""
    admin: User = test_setup["admin"]
    fake_case_id = uuid.uuid4()

    response = client.patch(
        f"/api/v1/cases/{fake_case_id}/status",
        json={"status": "in_progress"},
        headers=auth_header(admin),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_patch_case_status_invalid_enum_value(client: TestClient, test_setup: dict) -> None:
    """Verify invalid status string returns HTTP 422 VALIDATION_ERROR."""
    org: Organization = test_setup["org"]
    admin: User = test_setup["admin"]

    create_res = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Dossier Enum Invalide"},
        headers=auth_header(admin),
    )
    case_id = create_res.json()["id"]

    response = client.patch(
        f"/api/v1/cases/{case_id}/status",
        json={"status": "destroyed"},
        headers=auth_header(admin),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# =========================================================================
# 5. GET /api/v1/cases (Global Cross-Tenant User Cases Listing) & Zero Leak
# =========================================================================


def test_cross_tenant_isolation_fails(client: TestClient, test_setup: dict) -> None:
    """Verify strict cross-tenant isolation (Zero Leak) rejects access with HTTP 403.

    Given a user belonging exclusively to organization B (other_admin),
    When they attempt to access case-alpha belonging to organization A,
    Then verify_case_access rejects access with HTTP 403 Forbidden and code INSUFFICIENT_PERMISSIONS
    without disclosing any case metadata or existence details.
    """
    org: Organization = test_setup["org"]
    admin: User = test_setup["admin"]
    other_admin: User = test_setup["other_admin"]

    create_res = client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Case Alpha (Top Secret)", "description": "Données sensibles org A"},
        headers=auth_header(admin),
    )
    assert create_res.status_code == 201
    case_id = create_res.json()["id"]

    # Attempt cross-tenant access from user in Org B
    response = client.get(
        f"/api/v1/cases/{case_id}",
        headers=auth_header(other_admin),
    )
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
    assert data["error"]["message"] == "Accès refusé à ce dossier."
    # Ensure zero metadata leakage
    assert "title" not in data
    assert "description" not in data
    assert "status" not in data
    assert "id" not in data


def test_list_user_cases_nominal_multi_org(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify GET /api/v1/cases aggregates cases from all orgs where the user
    is an active member.
    """
    org: Organization = test_setup["org"]
    other_org: Organization = test_setup["other_org"]
    admin: User = test_setup["admin"]
    other_admin: User = test_setup["other_admin"]
    analyst: User = test_setup["analyst"]

    # Add analyst to other_org as well (multi-membership)
    db_session.add(
        Membership(
            organization_id=other_org.id,
            user_id=analyst.id,
            role=MembershipRole.ANALYST.value,
        )
    )
    db_session.commit()

    # Create cases in org (Org A)
    client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Org A Case 1"},
        headers=auth_header(admin),
    )
    time.sleep(0.005)
    client.post(
        f"/api/v1/organizations/{org.id}/cases",
        json={"title": "Org A Case 2"},
        headers=auth_header(admin),
    )

    # Create case in other_org (Org B)
    time.sleep(0.005)
    client.post(
        f"/api/v1/organizations/{other_org.id}/cases",
        json={"title": "Org B Case 1"},
        headers=auth_header(other_admin),
    )

    # Third org where analyst is NOT a member
    user_svc = UserService(db_session)
    org_svc = OrganizationService(db_session)
    secret_creator = user_svc.create_user(
        UserCreate(email="secret@sec.iryx", password="Password123!")
    )
    third_org = org_svc.create_organization(name="CERT Tierce", creator_id=secret_creator.id)
    client.post(
        f"/api/v1/organizations/{third_org.id}/cases",
        json={"title": "Secret Third Org Case"},
        headers=auth_header(secret_creator),
    )

    # Query GET /api/v1/cases as analyst
    response = client.get("/api/v1/cases?limit=20&offset=0", headers=auth_header(analyst))
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 3
    assert len(data["items"]) == 3
    titles = [item["title"] for item in data["items"]]
    assert titles == ["Org B Case 1", "Org A Case 2", "Org A Case 1"]
    assert "Secret Third Org Case" not in titles


def test_list_user_cases_pagination_multi_page(
    client: TestClient, test_setup: dict
) -> None:
    """Verify GET /api/v1/cases multi-page pagination and has_more behavior."""
    org: Organization = test_setup["org"]
    admin: User = test_setup["admin"]

    for i in range(3):
        time.sleep(0.005)
        client.post(
            f"/api/v1/organizations/{org.id}/cases",
            json={"title": f"Pagination Multi Case {i + 1}"},
            headers=auth_header(admin),
        )

    # Page 1: limit=2, offset=0
    r1 = client.get("/api/v1/cases?limit=2&offset=0", headers=auth_header(admin))
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["limit"] == 2
    assert d1["offset"] == 0
    assert len(d1["items"]) == 2
    assert d1["has_more"] is True

    # Page 2: limit=2, offset=2
    r2 = client.get("/api/v1/cases?limit=2&offset=2", headers=auth_header(admin))
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["limit"] == 2
    assert d2["offset"] == 2
    assert len(d2["items"]) == 1
    assert d2["has_more"] is False


def test_list_user_cases_outsider_returns_empty(client: TestClient, test_setup: dict) -> None:
    """Verify GET /api/v1/cases by user without memberships returns empty collection."""
    outsider: User = test_setup["outsider"]

    response = client.get("/api/v1/cases", headers=auth_header(outsider))
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["has_more"] is False


def test_list_user_cases_pagination_validation_returns_422(
    client: TestClient, test_setup: dict
) -> None:
    """Verify GET /api/v1/cases rejects invalid pagination bounds with HTTP 422 VALIDATION_ERROR."""
    admin: User = test_setup["admin"]

    # limit = 0
    r0 = client.get("/api/v1/cases?limit=0", headers=auth_header(admin))
    assert r0.status_code == 422
    assert r0.json()["error"]["code"] == "VALIDATION_ERROR"

    # limit = 101
    r101 = client.get("/api/v1/cases?limit=101", headers=auth_header(admin))
    assert r101.status_code == 422
    assert r101.json()["error"]["code"] == "VALIDATION_ERROR"

    # offset = -1
    r_neg = client.get("/api/v1/cases?offset=-1", headers=auth_header(admin))
    assert r_neg.status_code == 422
    assert r_neg.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_case_not_found_standardized_message(client: TestClient, test_setup: dict) -> None:
    """Verify GET /api/v1/cases/{fake_uuid} returns standardized 404 error envelope."""
    admin: User = test_setup["admin"]
    fake_case_id = uuid.uuid4()

    response = client.get(f"/api/v1/cases/{fake_case_id}", headers=auth_header(admin))
    assert response.status_code == 404
    data = response.json()
    assert data == {
        "error": {
            "code": "CASE_NOT_FOUND",
            "message": "Le dossier demandé n'existe pas.",
        }
    }
