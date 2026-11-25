"""Integration tests for Findings API endpoints (/api/v1/cases/{case_id}/findings)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from iryx.analytics.models import (
    Finding,
    FindingConfidence,
    FindingSeverity,
    FindingStatus,
    FindingType,
)
from iryx.auth.models import MembershipRole, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.models import Case
from iryx.core.security import create_access_token
from iryx.organizations.services import OrganizationService


@pytest.fixture
def test_setup(db_session: Session) -> dict[str, object]:
    """Create test organization, users, and cases for tenant isolation testing."""
    user_svc = UserService(db_session)
    org_svc = OrganizationService(db_session)

    admin = user_svc.create_user(UserCreate(email="admin@soc.iryx", password="Password123!"))
    investigator = user_svc.create_user(
        UserCreate(email="investigator@soc.iryx", password="Password123!")
    )
    analyst = user_svc.create_user(UserCreate(email="analyst@soc.iryx", password="Password123!"))
    viewer = user_svc.create_user(UserCreate(email="viewer@soc.iryx", password="Password123!"))
    outsider = user_svc.create_user(UserCreate(email="outsider@soc.iryx", password="Password123!"))

    # Create Org 1
    org = org_svc.create_organization(name="CERT Interne", creator_id=admin.id)
    org_svc.add_member(org_id=org.id, user_id=investigator.id, role=MembershipRole.INVESTIGATOR)
    org_svc.add_member(org_id=org.id, user_id=analyst.id, role=MembershipRole.ANALYST)
    org_svc.add_member(org_id=org.id, user_id=viewer.id, role=MembershipRole.VIEWER)

    case = Case(organization_id=org.id, title="Affaire Ransomware", created_by=investigator.id)
    db_session.add(case)
    db_session.commit()

    # Create Org 2 for tenant isolation
    other_admin = user_svc.create_user(
        UserCreate(email="other_admin@external.iryx", password="Password123!")
    )
    other_org = org_svc.create_organization(name="CERT Externe", creator_id=other_admin.id)
    other_case = Case(
        organization_id=other_org.id, title="Affaire Concurrente", created_by=other_admin.id
    )
    db_session.add(other_case)
    db_session.commit()

    return {
        "org": org,
        "other_org": other_org,
        "case": case,
        "other_case": other_case,
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
# 1. POST /api/v1/cases/{case_id}/findings (Create Finding)
# =========================================================================


def test_create_finding_nominal(client: TestClient, test_setup: dict) -> None:
    """Verify nominal finding creation by analyst returns HTTP 201 with status proposed."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    obs_ref = str(uuid.uuid4())
    tool_ref = str(uuid.uuid4())

    payload = {
        "title": "Exfiltration de données via canal DNS",
        "severity": "high",
        "confidence": "high",
        "finding_type": "inference",
        "observation_refs": [obs_ref],
        "tool_execution_refs": [tool_ref],
    }

    response = client.post(
        f"/api/v1/cases/{case.id}/findings",
        json=payload,
        headers=auth_header(analyst),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Exfiltration de données via canal DNS"
    assert data["severity"] == "high"
    assert data["confidence"] == "high"
    assert data["finding_type"] == "inference"
    assert data["status"] == "proposed"
    assert data["observation_refs"] == [obs_ref]
    assert data["tool_execution_refs"] == [tool_ref]
    assert data["case_id"] == str(case.id)
    assert data["created_by"] == str(analyst.id)
    assert "id" in data
    assert "created_at" in data


def test_create_finding_with_empty_refs_nominal(client: TestClient, test_setup: dict) -> None:
    """Verify creating a finding with empty reference lists is accepted."""
    case: Case = test_setup["case"]
    investigator: User = test_setup["investigator"]

    payload = {
        "title": "Détection préliminaire sans artefact immédiat",
        "severity": "medium",
        "observation_refs": [],
        "tool_execution_refs": [],
    }

    response = client.post(
        f"/api/v1/cases/{case.id}/findings",
        json=payload,
        headers=auth_header(investigator),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["observation_refs"] == []
    assert data["tool_execution_refs"] == []
    assert data["confidence"] == "medium"
    assert data["finding_type"] == "fact"


def test_create_finding_invalid_severity_422(client: TestClient, test_setup: dict) -> None:
    """Verify invalid severity value triggers HTTP 422 Unprocessable Entity."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    payload = {
        "title": "Constat à sévérité invalide",
        "severity": "extreme",
    }

    response = client.post(
        f"/api/v1/cases/{case.id}/findings",
        json=payload,
        headers=auth_header(analyst),
    )

    assert response.status_code == 422


def test_create_finding_invalid_finding_type_422(client: TestClient, test_setup: dict) -> None:
    """Verify invalid finding_type value triggers HTTP 422 Unprocessable Entity."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    payload = {
        "title": "Constat à type invalide",
        "severity": "low",
        "finding_type": "guess",
    }

    response = client.post(
        f"/api/v1/cases/{case.id}/findings",
        json=payload,
        headers=auth_header(analyst),
    )

    assert response.status_code == 422


def test_create_finding_whitespace_title_422(client: TestClient, test_setup: dict) -> None:
    """Verify empty or whitespace-only title triggers HTTP 422."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    response = client.post(
        f"/api/v1/cases/{case.id}/findings",
        json={"title": "   ", "severity": "low"},
        headers=auth_header(analyst),
    )
    assert response.status_code == 422


def test_create_finding_cross_tenant_forbidden_403(client: TestClient, test_setup: dict) -> None:
    """Verify user from another organization cannot create a finding (HTTP 403)."""
    case: Case = test_setup["case"]
    other_admin: User = test_setup["other_admin"]

    payload = {
        "title": "Tentative frauduleuse inter-tenant",
        "severity": "high",
    }

    response = client.post(
        f"/api/v1/cases/{case.id}/findings",
        json=payload,
        headers=auth_header(other_admin),
    )

    assert response.status_code == 403


def test_create_finding_nonexistent_case_404(client: TestClient, test_setup: dict) -> None:
    """Verify attempting to create finding on nonexistent case returns HTTP 404."""
    analyst: User = test_setup["analyst"]
    fake_case_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/cases/{fake_case_id}/findings",
        json={"title": "Finding fantôme", "severity": "low"},
        headers=auth_header(analyst),
    )

    assert response.status_code == 404


def test_viewer_role_forbidden_on_post_patch_delete(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify VIEWER role cannot create, update, or delete findings (HTTP 403)."""
    case: Case = test_setup["case"]
    viewer: User = test_setup["viewer"]

    # Pre-create a finding in DB
    finding = Finding(case_id=case.id, title="Constat Existant")
    db_session.add(finding)
    db_session.commit()

    # 1. POST by viewer -> 403
    resp_post = client.post(
        f"/api/v1/cases/{case.id}/findings",
        json={"title": "Constat par viewer", "severity": "low"},
        headers=auth_header(viewer),
    )
    assert resp_post.status_code == 403

    # 2. PATCH by viewer -> 403
    resp_patch = client.patch(
        f"/api/v1/cases/{case.id}/findings/{finding.id}",
        json={"title": "Tentative modif viewer"},
        headers=auth_header(viewer),
    )
    assert resp_patch.status_code == 403

    # 3. DELETE by viewer -> 403
    resp_delete = client.delete(
        f"/api/v1/cases/{case.id}/findings/{finding.id}",
        headers=auth_header(viewer),
    )
    assert resp_delete.status_code == 403

    # But GET by viewer -> 200 OK
    resp_get = client.get(
        f"/api/v1/cases/{case.id}/findings/{finding.id}",
        headers=auth_header(viewer),
    )
    assert resp_get.status_code == 200


# =========================================================================
# 2. GET /api/v1/cases/{case_id}/findings (List Findings)
# =========================================================================


def test_list_findings_with_filters_and_pagination(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify listing findings supports pagination, determinism, and all filters."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    # Pre-populate findings directly in DB
    f1 = Finding(
        case_id=case.id,
        title="Constat F1",
        severity=FindingSeverity.HIGH,
        confidence=FindingConfidence.MEDIUM,
        finding_type=FindingType.FACT,
        status=FindingStatus.PROPOSED,
    )
    f2 = Finding(
        case_id=case.id,
        title="Constat F2",
        severity=FindingSeverity.CRITICAL,
        confidence=FindingConfidence.HIGH,
        finding_type=FindingType.INFERENCE,
        status=FindingStatus.VALIDATED,
    )
    f3 = Finding(
        case_id=case.id,
        title="Constat F3",
        severity=FindingSeverity.LOW,
        confidence=FindingConfidence.LOW,
        finding_type=FindingType.HYPOTHESIS,
        status=FindingStatus.PROPOSED,
    )
    db_session.add_all([f1, f2, f3])
    db_session.commit()

    # 1. Nominal list all
    resp = client.get(
        f"/api/v1/cases/{case.id}/findings",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3

    # 2. Filter by status=validated
    resp_val = client.get(
        f"/api/v1/cases/{case.id}/findings?status=validated",
        headers=auth_header(analyst),
    )
    assert resp_val.status_code == 200
    assert resp_val.json()["total"] == 1
    assert resp_val.json()["items"][0]["title"] == "Constat F2"

    # 3. Filter by severity=critical
    resp_crit = client.get(
        f"/api/v1/cases/{case.id}/findings?severity=critical",
        headers=auth_header(analyst),
    )
    assert resp_crit.status_code == 200
    assert resp_crit.json()["total"] == 1
    assert resp_crit.json()["items"][0]["title"] == "Constat F2"

    # 4. Filter by confidence=high
    resp_conf = client.get(
        f"/api/v1/cases/{case.id}/findings?confidence=high",
        headers=auth_header(analyst),
    )
    assert resp_conf.status_code == 200
    assert resp_conf.json()["total"] == 1
    assert resp_conf.json()["items"][0]["title"] == "Constat F2"

    # 5. Filter by finding_type=inference
    resp_type = client.get(
        f"/api/v1/cases/{case.id}/findings?finding_type=inference",
        headers=auth_header(analyst),
    )
    assert resp_type.status_code == 200
    assert resp_type.json()["total"] == 1
    assert resp_type.json()["items"][0]["title"] == "Constat F2"

    # 6. Pagination limit=1, offset=1
    resp_page = client.get(
        f"/api/v1/cases/{case.id}/findings?limit=1&offset=1",
        headers=auth_header(analyst),
    )
    assert resp_page.status_code == 200
    data_page = resp_page.json()
    assert data_page["total"] == 3
    assert len(data_page["items"]) == 1
    assert data_page["limit"] == 1
    assert data_page["offset"] == 1
    assert data_page["has_more"] is True


def test_list_findings_scoping_excludes_other_case(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify list_findings strictly returns findings of the requested case only."""
    case: Case = test_setup["case"]
    other_case: Case = test_setup["other_case"]
    analyst: User = test_setup["analyst"]

    f_case1 = Finding(case_id=case.id, title="Finding Case 1")
    f_case2 = Finding(case_id=other_case.id, title="Finding Case 2")
    db_session.add_all([f_case1, f_case2])
    db_session.commit()

    resp = client.get(f"/api/v1/cases/{case.id}/findings", headers=auth_header(analyst))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Finding Case 1"


def test_list_findings_cross_tenant_forbidden_403(client: TestClient, test_setup: dict) -> None:
    """Verify listing findings from unauthorized tenant returns HTTP 403."""
    case: Case = test_setup["case"]
    outsider: User = test_setup["outsider"]

    response = client.get(
        f"/api/v1/cases/{case.id}/findings",
        headers=auth_header(outsider),
    )
    assert response.status_code == 403


# =========================================================================
# 3. GET, PATCH & DELETE /api/v1/cases/{case_id}/findings/{finding_id}
# =========================================================================


def test_get_finding_detail_nominal(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify retrieving finding details returns HTTP 200 with full fields."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    finding = Finding(
        case_id=case.id,
        title="Détail Constat",
        severity=FindingSeverity.MEDIUM,
        confidence=FindingConfidence.HIGH,
        finding_type=FindingType.FACT,
    )
    db_session.add(finding)
    db_session.commit()

    resp = client.get(
        f"/api/v1/cases/{case.id}/findings/{finding.id}",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(finding.id)
    assert data["title"] == "Détail Constat"


def test_get_finding_not_found_404(client: TestClient, test_setup: dict) -> None:
    """Verify querying non-existent finding returns HTTP 404."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    fake_id = uuid.uuid4()

    resp = client.get(
        f"/api/v1/cases/{case.id}/findings/{fake_id}",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 404


def test_cross_case_404_scoping(client: TestClient, test_setup: dict, db_session: Session) -> None:
    """Verify accessing/mutating Case A finding via Case B URL returns 404."""
    case: Case = test_setup["case"]
    other_case: Case = test_setup["other_case"]
    other_admin: User = test_setup["other_admin"]

    finding_in_case1 = Finding(case_id=case.id, title="Finding in Case 1")
    db_session.add(finding_in_case1)
    db_session.commit()

    # User in Org 2 has access to other_case, but finding_in_case1 belongs to case
    # 1. GET via Case B URL -> 404
    resp_get = client.get(
        f"/api/v1/cases/{other_case.id}/findings/{finding_in_case1.id}",
        headers=auth_header(other_admin),
    )
    assert resp_get.status_code == 404

    # 2. PATCH via Case B URL -> 404
    resp_patch = client.patch(
        f"/api/v1/cases/{other_case.id}/findings/{finding_in_case1.id}",
        json={"title": "Hacked Title"},
        headers=auth_header(other_admin),
    )
    assert resp_patch.status_code == 404

    # 3. DELETE via Case B URL -> 404
    resp_delete = client.delete(
        f"/api/v1/cases/{other_case.id}/findings/{finding_in_case1.id}",
        headers=auth_header(other_admin),
    )
    assert resp_delete.status_code == 404


def test_update_finding_nominal(client: TestClient, test_setup: dict, db_session: Session) -> None:
    """Verify updating finding attributes (status, severity, title) returns HTTP 200."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    finding = Finding(
        case_id=case.id,
        title="Constat Initial",
        severity=FindingSeverity.LOW,
        status=FindingStatus.PROPOSED,
    )
    db_session.add(finding)
    db_session.commit()

    update_payload = {
        "title": "Constat Réévalué",
        "severity": "critical",
        "confidence": "high",
        "status": "validated",
    }

    resp = client.patch(
        f"/api/v1/cases/{case.id}/findings/{finding.id}",
        json=update_payload,
        headers=auth_header(analyst),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Constat Réévalué"
    assert data["severity"] == "critical"
    assert data["confidence"] == "high"
    assert data["status"] == "validated"


def test_update_finding_refs_via_patch(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify updating observation and tool execution references via PATCH."""
    case: Case = test_setup["case"]
    investigator: User = test_setup["investigator"]

    old_obs = uuid.uuid4()
    finding = Finding(
        case_id=case.id,
        title="Constat Références",
        observation_refs=[old_obs],
        tool_execution_refs=[],
    )
    db_session.add(finding)
    db_session.commit()

    new_obs = str(uuid.uuid4())
    new_tool = str(uuid.uuid4())

    resp = client.patch(
        f"/api/v1/cases/{case.id}/findings/{finding.id}",
        json={"observation_refs": [new_obs], "tool_execution_refs": [new_tool]},
        headers=auth_header(investigator),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["observation_refs"] == [new_obs]
    assert data["tool_execution_refs"] == [new_tool]


def test_cross_tenant_forbidden_on_get_and_delete(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify cross-tenant GET and DELETE attempts return HTTP 403."""
    case: Case = test_setup["case"]
    other_admin: User = test_setup["other_admin"]

    finding = Finding(case_id=case.id, title="Constat Protégé")
    db_session.add(finding)
    db_session.commit()

    # GET on Org 1 case by Org 2 user -> 403
    resp_get = client.get(
        f"/api/v1/cases/{case.id}/findings/{finding.id}",
        headers=auth_header(other_admin),
    )
    assert resp_get.status_code == 403

    # DELETE on Org 1 case by Org 2 user -> 403
    resp_del = client.delete(
        f"/api/v1/cases/{case.id}/findings/{finding.id}",
        headers=auth_header(other_admin),
    )
    assert resp_del.status_code == 403


def test_delete_finding_nominal_and_subsequent_404(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify deleting a finding returns HTTP 204 and subsequent queries return 404."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    finding = Finding(case_id=case.id, title="Constat Éphémère")
    db_session.add(finding)
    db_session.commit()

    # 1. Delete finding
    resp = client.delete(
        f"/api/v1/cases/{case.id}/findings/{finding.id}",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 204

    # 2. Subsequent GET returns 404
    resp_get = client.get(
        f"/api/v1/cases/{case.id}/findings/{finding.id}",
        headers=auth_header(analyst),
    )
    assert resp_get.status_code == 404


# =========================================================================
# 6. POST /api/v1/cases/{case_id}/findings/{finding_id}/review (Gate H2 Review)
# =========================================================================


def test_review_finding_validate_nominal(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify validating a finding updates status to validated and adjusts attributes (FR19)."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    finding = Finding(
        case_id=case.id,
        title="Constat à valider",
        severity=FindingSeverity.LOW,
        confidence=FindingConfidence.LOW,
        status=FindingStatus.PROPOSED,
    )
    db_session.add(finding)
    db_session.commit()

    payload = {
        "action": "validate",
        "severity": "high",
        "confidence": "high",
    }

    response = client.post(
        f"/api/v1/cases/{case.id}/findings/{finding.id}/review",
        json=payload,
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(finding.id)
    assert data["status"] == "validated"
    assert data["severity"] == "high"
    assert data["confidence"] == "high"
    assert data["created_by"] == str(analyst.id)

    # Verify DB persistence
    refreshed = db_session.get(Finding, finding.id)
    assert refreshed.status == FindingStatus.VALIDATED
    assert refreshed.severity == FindingSeverity.HIGH
    assert refreshed.confidence == FindingConfidence.HIGH
    assert refreshed.created_by == analyst.id


def test_review_finding_reject_nominal(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify rejecting a finding updates its status to rejected."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    finding = Finding(
        case_id=case.id,
        title="Constat à rejeter",
        status=FindingStatus.PROPOSED,
    )
    db_session.add(finding)
    db_session.commit()

    payload = {"action": "reject"}

    response = client.post(
        f"/api/v1/cases/{case.id}/findings/{finding.id}/review",
        json=payload,
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"

    refreshed = db_session.get(Finding, finding.id)
    assert refreshed.status == FindingStatus.REJECTED


def test_review_finding_viewer_forbidden_403(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify user with VIEWER role cannot review a finding (HTTP 403 Forbidden)."""
    case: Case = test_setup["case"]
    viewer: User = test_setup["viewer"]

    finding = Finding(case_id=case.id, title="Constat Protégé Viewer")
    db_session.add(finding)
    db_session.commit()

    response = client.post(
        f"/api/v1/cases/{case.id}/findings/{finding.id}/review",
        json={"action": "validate"},
        headers=auth_header(viewer),
    )

    assert response.status_code == 403


def test_review_finding_cross_tenant_forbidden_403(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify cross-tenant finding review attempt returns HTTP 403 Forbidden."""
    case: Case = test_setup["case"]
    other_admin: User = test_setup["other_admin"]

    finding = Finding(case_id=case.id, title="Constat Cross Tenant")
    db_session.add(finding)
    db_session.commit()

    response = client.post(
        f"/api/v1/cases/{case.id}/findings/{finding.id}/review",
        json={"action": "validate"},
        headers=auth_header(other_admin),
    )

    assert response.status_code == 403


def test_review_finding_nonexistent_finding_404(
    client: TestClient, test_setup: dict
) -> None:
    """Verify reviewing nonexistent finding returns HTTP 404 Not Found."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    fake_finding_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/cases/{case.id}/findings/{fake_finding_id}/review",
        json={"action": "validate"},
        headers=auth_header(analyst),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "FINDING_NOT_FOUND"


def test_review_finding_invalid_action_422(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify invalid action returns HTTP 422 Unprocessable Content."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    finding = Finding(case_id=case.id, title="Constat Test Action")
    db_session.add(finding)
    db_session.commit()

    response = client.post(
        f"/api/v1/cases/{case.id}/findings/{finding.id}/review",
        json={"action": "archive"},
        headers=auth_header(analyst),
    )

    assert response.status_code == 422


def test_review_finding_reject_ignores_severity_and_confidence(
    client: TestClient, test_setup: dict, db_session: Session
) -> None:
    """Verify rejecting a finding does not modify its severity or confidence."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    finding = Finding(
        case_id=case.id,
        title="Constat Rejet Strict",
        severity=FindingSeverity.LOW,
        confidence=FindingConfidence.LOW,
        status=FindingStatus.PROPOSED,
    )
    db_session.add(finding)
    db_session.commit()

    payload = {
        "action": "reject",
        "severity": "critical",
        "confidence": "high",
    }

    response = client.post(
        f"/api/v1/cases/{case.id}/findings/{finding.id}/review",
        json=payload,
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["severity"] == "low"
    assert data["confidence"] == "low"

    refreshed = db_session.get(Finding, finding.id)
    assert refreshed.status == FindingStatus.REJECTED
    assert refreshed.severity == FindingSeverity.LOW
    assert refreshed.confidence == FindingConfidence.LOW
