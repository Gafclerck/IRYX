"""Unit tests for RBAC and Organization Membership FastAPI dependencies."""

import uuid

import pytest
from sqlalchemy.orm import Session

from iryx.auth.models import MembershipRole, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.core.exceptions import (
    InsufficientPermissionsException,
    OrganizationNotFoundException,
)
from iryx.organizations.dependencies import require_role, verify_org_membership
from iryx.organizations.services import OrganizationService


@pytest.fixture
def admin_user(db_session: Session) -> User:
    """Create admin test user."""
    return UserService(db_session).create_user(
        UserCreate(email="admin@iryx.local", password="Password12345!")
    )


@pytest.fixture
def analyst_user(db_session: Session) -> User:
    """Create analyst test user."""
    return UserService(db_session).create_user(
        UserCreate(email="analyst@iryx.local", password="Password12345!")
    )


@pytest.fixture
def viewer_user(db_session: Session) -> User:
    """Create viewer test user."""
    return UserService(db_session).create_user(
        UserCreate(email="viewer@iryx.local", password="Password12345!")
    )


@pytest.fixture
def outsider_user(db_session: Session) -> User:
    """Create outsider test user with no membership."""
    return UserService(db_session).create_user(
        UserCreate(email="outsider@iryx.local", password="Password12345!")
    )


def test_require_role_admin_success(db_session: Session, admin_user: User) -> None:
    """Verify require_role allows user holding the required role."""
    service = OrganizationService(db_session)
    org = service.create_organization("ANSSI SOC", creator_id=admin_user.id)

    dependency = require_role("admin")
    membership = dependency(org_id=org.id, current_user=admin_user, db=db_session)

    assert membership is not None
    assert membership.user_id == admin_user.id
    assert membership.role == "admin"


def test_require_role_insufficient_permissions(
    db_session: Session, admin_user: User, analyst_user: User
) -> None:
    """Verify require_role raises InsufficientPermissionsException for non-permitted role."""
    service = OrganizationService(db_session)
    org = service.create_organization("ANSSI SOC", creator_id=admin_user.id)
    service.add_member(org.id, analyst_user.id, role=MembershipRole.ANALYST)

    dependency = require_role("admin")
    with pytest.raises(InsufficientPermissionsException):
        dependency(org_id=org.id, current_user=analyst_user, db=db_session)


def test_require_role_non_member_raises_insufficient_permissions(
    db_session: Session, admin_user: User, outsider_user: User
) -> None:
    """Verify require_role raises InsufficientPermissionsException for non-members."""
    service = OrganizationService(db_session)
    org = service.create_organization("ANSSI SOC", creator_id=admin_user.id)

    dependency = require_role("admin")
    with pytest.raises(InsufficientPermissionsException):
        dependency(org_id=org.id, current_user=outsider_user, db=db_session)


def test_require_role_non_existent_org_raises_not_found(
    db_session: Session, admin_user: User
) -> None:
    """Verify require_role raises OrganizationNotFoundException when org does not exist."""
    dependency = require_role("admin")
    with pytest.raises(OrganizationNotFoundException):
        dependency(org_id=uuid.uuid4(), current_user=admin_user, db=db_session)


def test_require_role_multiple_roles(
    db_session: Session, admin_user: User, analyst_user: User, viewer_user: User
) -> None:
    """Verify require_role handles multiple allowed roles."""
    service = OrganizationService(db_session)
    org = service.create_organization("ANSSI SOC", creator_id=admin_user.id)
    service.add_member(org.id, analyst_user.id, role=MembershipRole.ANALYST)
    service.add_member(org.id, viewer_user.id, role=MembershipRole.VIEWER)

    guard = require_role("admin", "analyst")

    # Admin passes
    m1 = guard(org_id=org.id, current_user=admin_user, db=db_session)
    assert m1.role == "admin"

    # Analyst passes
    m2 = guard(org_id=org.id, current_user=analyst_user, db=db_session)
    assert m2.role == "analyst"

    # Viewer is denied
    with pytest.raises(InsufficientPermissionsException):
        guard(org_id=org.id, current_user=viewer_user, db=db_session)


def test_verify_org_membership_success(
    db_session: Session, admin_user: User, viewer_user: User
) -> None:
    """Verify verify_org_membership allows any role as long as user is a member."""
    service = OrganizationService(db_session)
    org = service.create_organization("ANSSI SOC", creator_id=admin_user.id)
    service.add_member(org.id, viewer_user.id, role=MembershipRole.VIEWER)

    m1 = verify_org_membership(org_id=org.id, current_user=admin_user, db=db_session)
    assert m1.user_id == admin_user.id

    m2 = verify_org_membership(org_id=org.id, current_user=viewer_user, db=db_session)
    assert m2.user_id == viewer_user.id


def test_verify_org_membership_non_member_fails(
    db_session: Session, admin_user: User, outsider_user: User
) -> None:
    """Verify verify_org_membership raises InsufficientPermissionsException for non-members."""
    service = OrganizationService(db_session)
    org = service.create_organization("ANSSI SOC", creator_id=admin_user.id)

    with pytest.raises(InsufficientPermissionsException):
        verify_org_membership(org_id=org.id, current_user=outsider_user, db=db_session)


def test_verify_org_membership_non_existent_org_fails(
    db_session: Session, admin_user: User
) -> None:
    """Verify verify_org_membership raises OrganizationNotFoundException when org does not exist."""
    with pytest.raises(OrganizationNotFoundException):
        verify_org_membership(org_id=uuid.uuid4(), current_user=admin_user, db=db_session)
