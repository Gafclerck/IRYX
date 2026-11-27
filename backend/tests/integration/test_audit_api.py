"""Integration tests for the immutable audit trail endpoint (Story 8.5)."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from iryx.analytics.models import Finding  # noqa: F401
from iryx.audit.models import AuditEvent
from iryx.audit.services import AuditService
from iryx.auth.models import MembershipRole, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.models import Case
from iryx.core.security import create_access_token
from iryx.organizations.services import OrganizationService

_AUDIT_TRAIL_PATH = "/api/v1/cases/{case_id}/audit-trail"


@pytest.fixture
def audit_setup(db_session: Session) -> dict[str, Any]:
    """Create an organization with admin/investigator/viewer members and one case."""
    user_service = UserService(db_session)
    organization_service = OrganizationService(db_session)

    admin = user_service.create_user(
        UserCreate(email="audit-admin@cert.fr", password="Password123!")
    )
    investigator = user_service.create_user(
        UserCreate(email="audit-investigator@cert.fr", password="Password123!")
    )
    viewer = user_service.create_user(
        UserCreate(email="audit-viewer@cert.fr", password="Password123!")
    )
    outsider = user_service.create_user(
        UserCreate(email="audit-outsider@cert.fr", password="Password123!")
    )

    organization = organization_service.create_organization(
        name="CERT Audit Trail", creator_id=admin.id
    )
    organization_service.add_member(
        org_id=organization.id, user_id=investigator.id, role=MembershipRole.INVESTIGATOR
    )
    organization_service.add_member(
        org_id=organization.id, user_id=viewer.id, role=MembershipRole.VIEWER
    )

    case = Case(organization_id=organization.id, title="Dossier audit", created_by=admin.id)
    db_session.add(case)
    db_session.commit()

    audit_service = AuditService(db_session)
    audit_service.record(
        action="CASE_CREATE",
        actor_id=admin.id,
        case_id=case.id,
        target_type="Case",
        target_id=case.id,
        details={"title": "Dossier audit"},
    )
    audit_service.record(
        action="CASE_STATUS_UPDATE",
        actor_id=investigator.id,
        case_id=case.id,
        target_type="Case",
        target_id=case.id,
        details={"status": "in_progress"},
    )
    db_session.commit()

    return {
        "admin": admin,
        "investigator": investigator,
        "viewer": viewer,
        "outsider": outsider,
        "organization": organization,
        "case": case,
    }


def _auth_header(user: User) -> dict[str, str]:
    """Build a Bearer header for the given user."""
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


def _audit_trail_url(case_id: uuid.UUID | str) -> str:
    """Return the audit trail endpoint for one case."""
    return _AUDIT_TRAIL_PATH.format(case_id=case_id)


def test_audit_trail_requires_authentication(client: TestClient) -> None:
    """Verify anonymous callers cannot consult an audit trail."""
    response = client.get(_audit_trail_url(uuid.uuid4()))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_audit_trail_rejects_invalid_token(client: TestClient) -> None:
    """Verify malformed bearer tokens are rejected before any read."""
    response = client.get(
        _audit_trail_url(uuid.uuid4()), headers={"Authorization": "Bearer invalid-token"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_audit_trail_unknown_case_returns_case_not_found(
    client: TestClient, audit_setup: dict[str, Any]
) -> None:
    """Verify a well-formed but unknown case identifier yields a 404 envelope."""
    response = client.get(
        _audit_trail_url(uuid.uuid4()), headers=_auth_header(audit_setup["admin"])
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_audit_trail_rejects_viewer_role(client: TestClient, audit_setup: dict[str, Any]) -> None:
    """Verify the viewer role is outside the audited admin/investigator matrix."""
    response = client.get(
        _audit_trail_url(audit_setup["case"].id), headers=_auth_header(audit_setup["viewer"])
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_audit_trail_rejects_non_member(client: TestClient, audit_setup: dict[str, Any]) -> None:
    """Verify a user without membership receives a 403 without leaking the trail."""
    response = client.get(
        _audit_trail_url(audit_setup["case"].id), headers=_auth_header(audit_setup["outsider"])
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_audit_trail_returns_case_events_for_admin_and_investigator(
    client: TestClient, audit_setup: dict[str, Any]
) -> None:
    """Verify admin and investigator roles read the immutable chronological trail."""
    admin_response = client.get(
        _audit_trail_url(audit_setup["case"].id), headers=_auth_header(audit_setup["admin"])
    )
    investigator_response = client.get(
        _audit_trail_url(audit_setup["case"].id), headers=_auth_header(audit_setup["investigator"])
    )

    for response in (admin_response, investigator_response):
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["total_items"] == 2
        assert data["limit"] == 100
        assert data["offset"] == 0
        assert data["has_more"] is False
        assert len(data["items"]) == 2
        assert [item["action"] for item in data["items"]] == [
            "CASE_CREATE",
            "CASE_STATUS_UPDATE",
        ]
        assert all(item["case_id"] == str(audit_setup["case"].id) for item in data["items"])


def test_audit_trail_pagination_limit_offset_and_validation(
    client: TestClient, audit_setup: dict[str, Any]
) -> None:
    """Verify page size, offset and bounds validation on the audit trail endpoint."""
    case_id = audit_setup["case"].id
    admin_headers = _auth_header(audit_setup["admin"])

    first_page = client.get(_audit_trail_url(case_id), params={"limit": 1}, headers=admin_headers)
    assert first_page.status_code == 200
    first_data = first_page.json()
    assert first_data["total"] == 2
    assert first_data["limit"] == 1
    assert first_data["offset"] == 0
    assert first_data["has_more"] is True
    assert len(first_data["items"]) == 1
    assert first_data["items"][0]["action"] == "CASE_CREATE"

    second_page = client.get(
        _audit_trail_url(case_id), params={"limit": 1, "offset": 1}, headers=admin_headers
    )
    assert second_page.status_code == 200
    second_data = second_page.json()
    assert second_data["has_more"] is False
    assert len(second_data["items"]) == 1
    assert second_data["items"][0]["action"] == "CASE_STATUS_UPDATE"

    invalid_responses = [
        client.get(_audit_trail_url(case_id), params={"limit": 0}, headers=admin_headers),
        client.get(_audit_trail_url(case_id), params={"limit": 101}, headers=admin_headers),
        client.get(_audit_trail_url(case_id), params={"offset": -1}, headers=admin_headers),
    ]
    for response in invalid_responses:
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_case_via_api_emits_case_create_audit(
    client: TestClient, db_session: Session, audit_setup: dict[str, Any]
) -> None:
    """Verify a case creation through the API is written to the immutable trail."""
    create_response = client.post(
        f"/api/v1/organizations/{audit_setup['organization'].id}/cases",
        json={"title": "Nouveau dossier audit", "description": None},
        headers=_auth_header(audit_setup["admin"]),
    )

    assert create_response.status_code == 201
    created_case_id = create_response.json()["id"]

    trail_response = client.get(
        _audit_trail_url(created_case_id), headers=_auth_header(audit_setup["admin"])
    )
    assert trail_response.status_code == 200
    trail_data = trail_response.json()
    assert trail_data["total"] == 1
    assert trail_data["items"][0]["action"] == "CASE_CREATE"
    assert trail_data["items"][0]["target_type"] == "Case"
    assert trail_data["items"][0]["actor_id"] == str(audit_setup["admin"].id)
    assert trail_data["items"][0]["details"]["title"] == "Nouveau dossier audit"


def test_login_via_api_emits_auth_login_audit(
    client: TestClient, db_session: Session, audit_setup: dict[str, Any]
) -> None:
    """Verify a successful login writes one AUTH_LOGIN row targeting the user."""
    admin = audit_setup["admin"]

    response = client.post(
        "/api/v1/auth/login", json={"email": admin.email, "password": "Password123!"}
    )

    assert response.status_code == 200
    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "AUTH_LOGIN")
    ).all()
    assert len(events) == 1
    assert events[0].case_id is None
    assert events[0].target_type == "User"
    assert events[0].target_id == admin.id
    assert events[0].actor_id == admin.id


def test_get_case_via_api_emits_case_read_audit(
    client: TestClient, db_session: Session, audit_setup: dict[str, Any]
) -> None:
    """Verify case consultation writes one CASE_READ row in the same transaction."""
    case = audit_setup["case"]

    response = client.get(f"/api/v1/cases/{case.id}", headers=_auth_header(audit_setup["admin"]))

    assert response.status_code == 200
    events = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.action == "CASE_READ", AuditEvent.target_id == case.id
        )
    ).all()
    assert len(events) == 1
    assert events[0].actor_id == audit_setup["admin"].id


def test_update_case_status_via_api_emits_case_status_update_audit(
    client: TestClient, db_session: Session, audit_setup: dict[str, Any]
) -> None:
    """Verify a status transition writes one CASE_STATUS_UPDATE row."""
    case = audit_setup["case"]
    before = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "CASE_STATUS_UPDATE")
    ).all()

    response = client.patch(
        f"/api/v1/cases/{case.id}/status",
        json={"status": "in_progress"},
        headers=_auth_header(audit_setup["admin"]),
    )

    assert response.status_code == 200
    after = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "CASE_STATUS_UPDATE")
    ).all()
    assert len(after) == len(before) + 1
    assert after[-1].target_id == case.id
    assert after[-1].details["status"] == "in_progress"


def test_report_list_path_does_not_write_audit(
    client: TestClient,
    audit_setup: dict[str, Any],
) -> None:
    """Verify Story 8.4 read endpoints stay audit-free while the trail is consulted."""
    case_id = audit_setup["case"].id
    admin_headers = _auth_header(audit_setup["admin"])

    before = client.get(_audit_trail_url(case_id), headers=admin_headers).json()["total"]

    reports_response = client.get(
        f"/api/v1/cases/{case_id}/reports",
        headers=admin_headers,
    )
    assert reports_response.status_code == 200
    assert reports_response.json()["total"] == 0

    after = client.get(_audit_trail_url(case_id), headers=admin_headers).json()["total"]
    assert after == before
