"""Integration tests for Organizations and RBAC API endpoints (/api/v1/organizations)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from iryx.auth.models import User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.core.security import create_access_token


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Create registered admin test user."""
    return UserService(db_session).create_user(
        UserCreate(email="admin@soc.iryx", password="SecurePassword123!")
    )


@pytest.fixture
def analyst_user(db_session: Session) -> User:
    """Create registered analyst test user."""
    return UserService(db_session).create_user(
        UserCreate(email="analyst@soc.iryx", password="SecurePassword123!")
    )


@pytest.fixture
def viewer_user(db_session: Session) -> User:
    """Create registered viewer test user."""
    return UserService(db_session).create_user(
        UserCreate(email="viewer@soc.iryx", password="SecurePassword123!")
    )


@pytest.fixture
def outsider_user(db_session: Session) -> User:
    """Create registered user with no organization membership."""
    return UserService(db_session).create_user(
        UserCreate(email="outsider@soc.iryx", password="SecurePassword123!")
    )


def auth_header(user: User) -> dict[str, str]:
    """Generate Authorization header with Bearer JWT for specified user."""
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


# -------------------------------------------------------------------------
# POST /api/v1/organizations (Create Organization)
# -------------------------------------------------------------------------


def test_create_organization_nominal(client: TestClient, admin_user: User) -> None:
    """Verify nominal POST /api/v1/organizations returns HTTP 201 with creator as admin."""
    response = client.post(
        "/api/v1/organizations",
        json={"name": "ANSSI SOC"},
        headers=auth_header(admin_user),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "ANSSI SOC"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

    # Verify admin membership was automatically created
    org_id = data["id"]
    members_resp = client.get(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth_header(admin_user),
    )
    assert members_resp.status_code == 200
    members_data = members_resp.json()
    assert members_data["total"] == 1
    assert members_data["items"][0]["user_id"] == str(admin_user.id)
    assert members_data["items"][0]["role"] == "admin"
    assert members_data["items"][0]["email"] == admin_user.email


def test_create_organization_unauthenticated(client: TestClient) -> None:
    """Verify POST /api/v1/organizations returns HTTP 401 when unauthenticated."""
    response = client.post("/api/v1/organizations", json={"name": "ANSSI SOC"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_create_organization_validation_error(client: TestClient, admin_user: User) -> None:
    """Verify POST /api/v1/organizations returns HTTP 422 for invalid payloads."""
    # Empty name
    r1 = client.post(
        "/api/v1/organizations",
        json={"name": ""},
        headers=auth_header(admin_user),
    )
    assert r1.status_code == 422
    assert r1.json()["error"]["code"] == "VALIDATION_ERROR"

    # Whitespace only
    r2 = client.post(
        "/api/v1/organizations",
        json={"name": "    "},
        headers=auth_header(admin_user),
    )
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "VALIDATION_ERROR"

    # Missing name
    r3 = client.post(
        "/api/v1/organizations",
        json={},
        headers=auth_header(admin_user),
    )
    assert r3.status_code == 422
    assert r3.json()["error"]["code"] == "VALIDATION_ERROR"


# -------------------------------------------------------------------------
# GET /api/v1/organizations (List User Organizations)
# -------------------------------------------------------------------------


def test_list_user_organizations_nominal(
    client: TestClient, admin_user: User, outsider_user: User
) -> None:
    """Verify GET /api/v1/organizations returns paginated list of user's orgs."""
    # Create two organizations with admin_user
    client.post(
        "/api/v1/organizations",
        json={"name": "Org 1"},
        headers=auth_header(admin_user),
    )
    client.post(
        "/api/v1/organizations",
        json={"name": "Org 2"},
        headers=auth_header(admin_user),
    )

    response = client.get(
        "/api/v1/organizations?limit=10&offset=0",
        headers=auth_header(admin_user),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["total_items"] == 2
    assert len(data["items"]) == 2
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert data["has_more"] is False

    # Outsider has 0 organizations
    outsider_resp = client.get(
        "/api/v1/organizations",
        headers=auth_header(outsider_user),
    )
    assert outsider_resp.status_code == 200
    assert outsider_resp.json()["total"] == 0
    assert len(outsider_resp.json()["items"]) == 0


def test_list_organizations_unauthenticated(client: TestClient) -> None:
    """Verify GET /api/v1/organizations returns HTTP 401 when unauthenticated."""
    response = client.get("/api/v1/organizations")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


# -------------------------------------------------------------------------
# GET /api/v1/organizations/{org_id} (Retrieve Organization)
# -------------------------------------------------------------------------


def test_get_organization_by_member(client: TestClient, admin_user: User) -> None:
    """Verify GET /api/v1/organizations/{org_id} returns HTTP 200 for member."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "CERT-FR"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    response = client.get(
        f"/api/v1/organizations/{org_id}",
        headers=auth_header(admin_user),
    )
    assert response.status_code == 200
    assert response.json()["id"] == org_id
    assert response.json()["name"] == "CERT-FR"


def test_get_organization_zero_leak_non_member(
    client: TestClient, admin_user: User, outsider_user: User
) -> None:
    """Verify non-member receives HTTP 404 (Zero Leak principle)."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "Private Org"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    response = client.get(
        f"/api/v1/organizations/{org_id}",
        headers=auth_header(outsider_user),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORGANIZATION_NOT_FOUND"


def test_get_organization_non_existent(client: TestClient, admin_user: User) -> None:
    """Verify unknown org returns HTTP 404."""
    random_id = uuid.uuid4()
    response = client.get(
        f"/api/v1/organizations/{random_id}",
        headers=auth_header(admin_user),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORGANIZATION_NOT_FOUND"


# -------------------------------------------------------------------------
# POST /api/v1/organizations/{org_id}/members (Add Member)
# -------------------------------------------------------------------------


def test_add_member_by_admin_nominal(
    client: TestClient, admin_user: User, analyst_user: User
) -> None:
    """Verify adding a member by admin returns HTTP 201 with MemberOut schema."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    response = client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(analyst_user.id), "role": "analyst"},
        headers=auth_header(admin_user),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["organization_id"] == org_id
    assert data["user_id"] == str(analyst_user.id)
    assert data["role"] == "analyst"
    assert data["email"] == analyst_user.email
    assert "id" in data
    assert "created_at" in data


def test_add_member_unknown_user(client: TestClient, admin_user: User) -> None:
    """Verify adding non-existent user returns HTTP 404 USER_NOT_FOUND."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    random_user_id = str(uuid.uuid4())
    response = client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": random_user_id, "role": "analyst"},
        headers=auth_header(admin_user),
    )
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "USER_NOT_FOUND",
            "message": "Utilisateur introuvable.",
        }
    }


def test_add_member_unknown_organization(
    client: TestClient, admin_user: User, analyst_user: User
) -> None:
    """Verify adding member on non-existent org returns HTTP 404 ORGANIZATION_NOT_FOUND."""
    random_org_id = str(uuid.uuid4())
    response = client.post(
        f"/api/v1/organizations/{random_org_id}/members",
        json={"user_id": str(analyst_user.id), "role": "analyst"},
        headers=auth_header(admin_user),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORGANIZATION_NOT_FOUND"


def test_add_member_already_exists(
    client: TestClient, admin_user: User, analyst_user: User
) -> None:
    """Verify adding duplicate member returns HTTP 409 MEMBER_ALREADY_EXISTS."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    # First add
    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(analyst_user.id), "role": "analyst"},
        headers=auth_header(admin_user),
    )

    # Second add -> conflict
    response = client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(analyst_user.id), "role": "investigator"},
        headers=auth_header(admin_user),
    )
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "MEMBER_ALREADY_EXISTS",
            "message": "Cet utilisateur est déjà membre de l'organisation.",
        }
    }


def test_add_member_insufficient_permissions(
    client: TestClient,
    admin_user: User,
    analyst_user: User,
    viewer_user: User,
    outsider_user: User,
) -> None:
    """Verify non-admin cannot add members (HTTP 403 INSUFFICIENT_PERMISSIONS)."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    # Add analyst and viewer to org
    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(analyst_user.id), "role": "analyst"},
        headers=auth_header(admin_user),
    )
    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(viewer_user.id), "role": "viewer"},
        headers=auth_header(admin_user),
    )

    # Analyst tries to add
    r_analyst = client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(outsider_user.id), "role": "viewer"},
        headers=auth_header(analyst_user),
    )
    assert r_analyst.status_code == 403
    assert r_analyst.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

    # Viewer tries to add
    r_viewer = client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(outsider_user.id), "role": "viewer"},
        headers=auth_header(viewer_user),
    )
    assert r_viewer.status_code == 403
    assert r_viewer.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


# -------------------------------------------------------------------------
# GET /api/v1/organizations/{org_id}/members (List Members)
# -------------------------------------------------------------------------


def test_list_members_by_member(client: TestClient, admin_user: User, analyst_user: User) -> None:
    """Verify member can list members with pagination."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(analyst_user.id), "role": "analyst"},
        headers=auth_header(admin_user),
    )

    # Analyst lists members
    response = client.get(
        f"/api/v1/organizations/{org_id}/members?limit=20&offset=0",
        headers=auth_header(analyst_user),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    emails = {item["email"] for item in data["items"]}
    assert emails == {admin_user.email, analyst_user.email}


def test_list_members_pagination(
    client: TestClient, admin_user: User, analyst_user: User, viewer_user: User
) -> None:
    """Verify multi-page member pagination with limit, offset, slicing, and has_more."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Pagination Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(analyst_user.id), "role": "analyst"},
        headers=auth_header(admin_user),
    )
    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(viewer_user.id), "role": "viewer"},
        headers=auth_header(admin_user),
    )

    # Page 1: limit=2, offset=0
    resp_page_1 = client.get(
        f"/api/v1/organizations/{org_id}/members?limit=2&offset=0",
        headers=auth_header(admin_user),
    )
    assert resp_page_1.status_code == 200
    data_1 = resp_page_1.json()
    assert data_1["total"] == 3
    assert data_1["total_items"] == 3
    assert data_1["limit"] == 2
    assert data_1["offset"] == 0
    assert len(data_1["items"]) == 2
    assert data_1["has_more"] is True

    # Page 2: limit=2, offset=2
    resp_page_2 = client.get(
        f"/api/v1/organizations/{org_id}/members?limit=2&offset=2",
        headers=auth_header(admin_user),
    )
    assert resp_page_2.status_code == 200
    data_2 = resp_page_2.json()
    assert data_2["total"] == 3
    assert data_2["total_items"] == 3
    assert data_2["limit"] == 2
    assert data_2["offset"] == 2
    assert len(data_2["items"]) == 1
    assert data_2["has_more"] is False

    # Check slicing: items across pages do not overlap and cover all 3 members
    ids_1 = [m["id"] for m in data_1["items"]]
    ids_2 = [m["id"] for m in data_2["items"]]
    assert set(ids_1).isdisjoint(set(ids_2))
    assert len(set(ids_1 + ids_2)) == 3


def test_list_members_by_non_member_forbidden(
    client: TestClient, admin_user: User, outsider_user: User
) -> None:
    """Verify non-member receives HTTP 403 when attempting to list members."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    response = client.get(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth_header(outsider_user),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


# -------------------------------------------------------------------------
# PATCH /api/v1/organizations/{org_id}/members/{user_id} (Update Role)
# -------------------------------------------------------------------------


def test_update_member_role_by_admin(
    client: TestClient, admin_user: User, analyst_user: User
) -> None:
    """Verify admin can update member role."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(analyst_user.id), "role": "analyst"},
        headers=auth_header(admin_user),
    )

    response = client.patch(
        f"/api/v1/organizations/{org_id}/members/{analyst_user.id}",
        json={"role": "investigator"},
        headers=auth_header(admin_user),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "investigator"
    assert data["user_id"] == str(analyst_user.id)
    assert data["email"] == analyst_user.email


def test_update_member_role_by_non_admin_forbidden(
    client: TestClient, admin_user: User, analyst_user: User, viewer_user: User
) -> None:
    """Verify non-admin cannot update roles (HTTP 403 INSUFFICIENT_PERMISSIONS)."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(analyst_user.id), "role": "analyst"},
        headers=auth_header(admin_user),
    )
    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(viewer_user.id), "role": "viewer"},
        headers=auth_header(admin_user),
    )

    response = client.patch(
        f"/api/v1/organizations/{org_id}/members/{analyst_user.id}",
        json={"role": "admin"},
        headers=auth_header(viewer_user),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_update_member_role_unknown_member(
    client: TestClient, admin_user: User, outsider_user: User
) -> None:
    """Verify updating non-existent member returns HTTP 404 MEMBER_NOT_FOUND."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{org_id}/members/{outsider_user.id}",
        json={"role": "investigator"},
        headers=auth_header(admin_user),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MEMBER_NOT_FOUND"


def test_update_member_role_cannot_demote_last_admin(client: TestClient, admin_user: User) -> None:
    """Verify demoting only admin returns HTTP 400 CANNOT_REMOVE_LAST_ADMIN."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    response = client.patch(
        f"/api/v1/organizations/{org_id}/members/{admin_user.id}",
        json={"role": "analyst"},
        headers=auth_header(admin_user),
    )
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "CANNOT_REMOVE_LAST_ADMIN",
            "message": "Impossible de supprimer ou rétrograder le dernier administrateur actif.",
        }
    }


# -------------------------------------------------------------------------
# DELETE /api/v1/organizations/{org_id}/members/{user_id} (Remove Member)
# -------------------------------------------------------------------------


def test_delete_member_by_admin_nominal(
    client: TestClient, admin_user: User, analyst_user: User
) -> None:
    """Verify admin can remove a member with HTTP 204 No Content."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(analyst_user.id), "role": "analyst"},
        headers=auth_header(admin_user),
    )

    response = client.delete(
        f"/api/v1/organizations/{org_id}/members/{analyst_user.id}",
        headers=auth_header(admin_user),
    )
    assert response.status_code == 204
    assert response.text == ""

    # Verify member is gone
    members_resp = client.get(
        f"/api/v1/organizations/{org_id}/members",
        headers=auth_header(admin_user),
    )
    assert members_resp.json()["total"] == 1


def test_delete_member_by_non_admin_forbidden(
    client: TestClient, admin_user: User, analyst_user: User, viewer_user: User
) -> None:
    """Verify non-admin cannot delete members (HTTP 403 INSUFFICIENT_PERMISSIONS)."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(analyst_user.id), "role": "analyst"},
        headers=auth_header(admin_user),
    )
    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(viewer_user.id), "role": "viewer"},
        headers=auth_header(admin_user),
    )

    response = client.delete(
        f"/api/v1/organizations/{org_id}/members/{analyst_user.id}",
        headers=auth_header(viewer_user),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_delete_member_unknown_member(
    client: TestClient, admin_user: User, outsider_user: User
) -> None:
    """Verify deleting non-existent member returns HTTP 404 MEMBER_NOT_FOUND."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    response = client.delete(
        f"/api/v1/organizations/{org_id}/members/{outsider_user.id}",
        headers=auth_header(admin_user),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MEMBER_NOT_FOUND"


def test_delete_member_cannot_remove_last_admin(client: TestClient, admin_user: User) -> None:
    """Verify deleting only admin returns HTTP 400 CANNOT_REMOVE_LAST_ADMIN."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    response = client.delete(
        f"/api/v1/organizations/{org_id}/members/{admin_user.id}",
        headers=auth_header(admin_user),
    )
    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "CANNOT_REMOVE_LAST_ADMIN",
            "message": "Impossible de supprimer ou rétrograder le dernier administrateur actif.",
        }
    }


def test_delete_member_can_remove_admin_if_second_admin_exists(
    db_session: Session, client: TestClient, admin_user: User, analyst_user: User
) -> None:
    """Verify an admin can be deleted if another admin exists in the organization."""
    create_resp = client.post(
        "/api/v1/organizations",
        json={"name": "SOC Team"},
        headers=auth_header(admin_user),
    )
    org_id = create_resp.json()["id"]

    # Add second admin
    client.post(
        f"/api/v1/organizations/{org_id}/members",
        json={"user_id": str(analyst_user.id), "role": "admin"},
        headers=auth_header(admin_user),
    )

    # First admin deletes second admin
    response = client.delete(
        f"/api/v1/organizations/{org_id}/members/{analyst_user.id}",
        headers=auth_header(admin_user),
    )
    assert response.status_code == 204
