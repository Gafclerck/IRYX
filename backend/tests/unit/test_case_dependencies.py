"""Unit tests for Cases security dependencies (verify_case_access, require_case_role)."""

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.auth.models import Membership, MembershipRole, Organization, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.dependencies import require_case_role, verify_case_access
from iryx.cases.models import Case, CaseStatus
from iryx.core.exceptions import (
    CaseNotFoundException,
    InsufficientPermissionsException,
)
from iryx.db.base import Base


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an in-memory SQLite database session isolated for dependency tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_setup(db_session: Session) -> dict[str, object]:
    """Create test organizations, users, and a case."""
    user_svc = UserService(db_session)

    admin = user_svc.create_user(UserCreate(email="admin@soc.iryx", password="Password123!"))
    investigator = user_svc.create_user(
        UserCreate(email="investigator@soc.iryx", password="Password123!")
    )
    analyst = user_svc.create_user(UserCreate(email="analyst@soc.iryx", password="Password123!"))
    viewer = user_svc.create_user(UserCreate(email="viewer@soc.iryx", password="Password123!"))
    outsider = user_svc.create_user(UserCreate(email="outsider@soc.iryx", password="Password123!"))

    org = Organization(name="CERT Interne")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)

    # Memberships for org
    for u, role in [
        (admin, MembershipRole.ADMIN),
        (investigator, MembershipRole.INVESTIGATOR),
        (analyst, MembershipRole.ANALYST),
        (viewer, MembershipRole.VIEWER),
    ]:
        db_session.add(
            Membership(
                organization_id=org.id,
                user_id=u.id,
                role=role.value,
            )
        )

    # Other org
    other_user = user_svc.create_user(
        UserCreate(email="other@external.iryx", password="Password123!")
    )
    other_org = Organization(name="CERT Externe")
    db_session.add(other_org)
    db_session.commit()
    db_session.refresh(other_org)

    db_session.add(
        Membership(
            organization_id=other_org.id,
            user_id=other_user.id,
            role=MembershipRole.ADMIN.value,
        )
    )

    # Case belonging to org
    case = Case(
        organization_id=org.id,
        title="Dossier Alpha",
        description="Investigation active",
        status=CaseStatus.OPEN,
        created_by=admin.id,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    return {
        "org": org,
        "other_org": other_org,
        "admin": admin,
        "investigator": investigator,
        "analyst": analyst,
        "viewer": viewer,
        "outsider": outsider,
        "other_user": other_user,
        "case": case,
    }


# =========================================================================
# 1. verify_case_access
# =========================================================================


def test_verify_case_access_nominal_for_all_org_roles(
    db_session: Session, test_setup: dict
) -> None:
    """Verify verify_case_access allows any active member of the owning organization."""
    case: Case = test_setup["case"]

    for role_name in ["admin", "investigator", "analyst", "viewer"]:
        user: User = test_setup[role_name]
        result = verify_case_access(case_id=case.id, current_user=user, db=db_session)
        assert result.id == case.id
        assert result.organization_id == case.organization_id


def test_verify_case_access_case_not_found_raises_404(
    db_session: Session, test_setup: dict
) -> None:
    """Verify verify_case_access raises CaseNotFoundException when case does not exist."""
    admin: User = test_setup["admin"]
    fake_case_id = uuid.uuid4()

    with pytest.raises(CaseNotFoundException) as exc_info:
        verify_case_access(case_id=fake_case_id, current_user=admin, db=db_session)

    assert exc_info.value.code == "CASE_NOT_FOUND"
    assert exc_info.value.status_code == 404
    assert exc_info.value.message == "Le dossier demandé n'existe pas."


def test_verify_case_access_outsider_raises_insufficient_permissions(
    db_session: Session, test_setup: dict
) -> None:
    """Verify verify_case_access raises InsufficientPermissionsException for non-member."""
    case: Case = test_setup["case"]
    outsider: User = test_setup["outsider"]

    with pytest.raises(InsufficientPermissionsException) as exc_info:
        verify_case_access(case_id=case.id, current_user=outsider, db=db_session)

    assert exc_info.value.code == "INSUFFICIENT_PERMISSIONS"
    assert exc_info.value.status_code == 403
    assert exc_info.value.message == "Accès refusé à ce dossier."


def test_verify_case_access_other_org_member_raises_insufficient_permissions(
    db_session: Session, test_setup: dict
) -> None:
    """Verify verify_case_access enforces tenant isolation against other org members."""
    case: Case = test_setup["case"]
    other_user: User = test_setup["other_user"]

    with pytest.raises(InsufficientPermissionsException) as exc_info:
        verify_case_access(case_id=case.id, current_user=other_user, db=db_session)

    assert exc_info.value.code == "INSUFFICIENT_PERMISSIONS"
    assert exc_info.value.status_code == 403
    assert exc_info.value.message == "Accès refusé à ce dossier."


# =========================================================================
# 2. require_case_role
# =========================================================================


def test_require_case_role_nominal_success(db_session: Session, test_setup: dict) -> None:
    """Verify require_case_role allows users holding one of the permitted roles."""
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]
    analyst: User = test_setup["analyst"]

    guard = require_case_role("admin", "analyst")

    r_admin = guard(case_id=case.id, current_user=admin, db=db_session)
    assert r_admin.id == case.id

    r_analyst = guard(case_id=case.id, current_user=analyst, db=db_session)
    assert r_analyst.id == case.id


def test_require_case_role_case_insensitive_normalization(
    db_session: Session, test_setup: dict
) -> None:
    """Verify require_case_role normalizes role strings to lowercase."""
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]
    analyst: User = test_setup["analyst"]
    viewer: User = test_setup["viewer"]

    guard = require_case_role("ADMIN", "Analyst")

    r_admin = guard(case_id=case.id, current_user=admin, db=db_session)
    assert r_admin.id == case.id

    r_analyst = guard(case_id=case.id, current_user=analyst, db=db_session)
    assert r_analyst.id == case.id

    with pytest.raises(InsufficientPermissionsException):
        guard(case_id=case.id, current_user=viewer, db=db_session)


def test_require_case_role_with_membership_enum(db_session: Session, test_setup: dict) -> None:
    """Verify require_case_role accepts MembershipRole enum instances."""
    case: Case = test_setup["case"]
    investigator: User = test_setup["investigator"]

    guard = require_case_role(MembershipRole.INVESTIGATOR)
    result = guard(case_id=case.id, current_user=investigator, db=db_session)
    assert result.id == case.id


def test_require_case_role_insufficient_role_raises_403(
    db_session: Session, test_setup: dict
) -> None:
    """Verify require_case_role raises 403 when user belongs to org but lacks required role."""
    case: Case = test_setup["case"]
    viewer: User = test_setup["viewer"]

    guard = require_case_role("admin", "investigator")

    with pytest.raises(InsufficientPermissionsException) as exc_info:
        guard(case_id=case.id, current_user=viewer, db=db_session)

    assert exc_info.value.code == "INSUFFICIENT_PERMISSIONS"
    assert exc_info.value.status_code == 403
    assert exc_info.value.message == "Accès refusé à ce dossier."


def test_require_case_role_outsider_raises_403(db_session: Session, test_setup: dict) -> None:
    """Verify require_case_role raises 403 for user not belonging to the case's organization."""
    case: Case = test_setup["case"]
    outsider: User = test_setup["outsider"]

    guard = require_case_role("admin")

    with pytest.raises(InsufficientPermissionsException) as exc_info:
        guard(case_id=case.id, current_user=outsider, db=db_session)

    assert exc_info.value.code == "INSUFFICIENT_PERMISSIONS"
    assert exc_info.value.status_code == 403


def test_require_case_role_case_not_found_raises_404(db_session: Session, test_setup: dict) -> None:
    """Verify require_case_role raises 404 when case does not exist."""
    admin: User = test_setup["admin"]
    fake_case_id = uuid.uuid4()

    guard = require_case_role("admin")

    with pytest.raises(CaseNotFoundException) as exc_info:
        guard(case_id=fake_case_id, current_user=admin, db=db_session)

    assert exc_info.value.code == "CASE_NOT_FOUND"
    assert exc_info.value.status_code == 404


def test_require_case_role_no_roles_specified_allows_any_member(
    db_session: Session, test_setup: dict
) -> None:
    """Verify require_case_role with no arguments behaves as membership check."""
    case: Case = test_setup["case"]
    viewer: User = test_setup["viewer"]
    outsider: User = test_setup["outsider"]

    guard = require_case_role()

    # Viewer passes
    r_viewer = guard(case_id=case.id, current_user=viewer, db=db_session)
    assert r_viewer.id == case.id

    # Outsider rejected
    with pytest.raises(InsufficientPermissionsException):
        guard(case_id=case.id, current_user=outsider, db=db_session)
