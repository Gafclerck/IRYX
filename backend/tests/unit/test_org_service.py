"""Unit tests for OrganizationService domain logic and RBAC invariants."""

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.auth.models import MembershipRole, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.core.exceptions import (
    CannotRemoveLastAdminException,
    MemberAlreadyExistsException,
    MemberNotFoundException,
    OrganizationNotFoundException,
    UserNotFoundException,
    ValidationException,
)
from iryx.db.base import Base
from iryx.organizations.services import OrganizationService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an in-memory SQLite database session isolated for unit testing."""
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
def user_a(db_session: Session) -> User:
    """Create test user A."""
    return UserService(db_session).create_user(
        UserCreate(email="user_a@iryx.local", password="Password12345!")
    )


@pytest.fixture
def user_b(db_session: Session) -> User:
    """Create test user B."""
    return UserService(db_session).create_user(
        UserCreate(email="user_b@iryx.local", password="Password12345!")
    )


@pytest.fixture
def user_c(db_session: Session) -> User:
    """Create test user C."""
    return UserService(db_session).create_user(
        UserCreate(email="user_c@iryx.local", password="Password12345!")
    )


def test_create_organization_assigns_creator_as_admin(db_session: Session, user_a: User) -> None:
    """Verify create_organization creates org and automatically makes creator an admin."""
    service = OrganizationService(db_session)
    org = service.create_organization(name="  ANSSI SOC  ", creator_id=user_a.id)

    assert org.id is not None
    assert org.name == "ANSSI SOC"

    # Verify membership
    members, total = service.list_members(org.id)
    assert total == 1
    assert len(members) == 1
    assert members[0].user_id == user_a.id
    assert members[0].role == MembershipRole.ADMIN.value
    assert members[0].email == user_a.email


def test_create_organization_empty_name_raises_validation_error(
    db_session: Session, user_a: User
) -> None:
    """Verify create_organization raises ValidationException on whitespace or empty name."""
    service = OrganizationService(db_session)
    with pytest.raises(ValidationException):
        service.create_organization(name="   ", creator_id=user_a.id)


def test_get_organization_by_id_nominal(db_session: Session, user_a: User) -> None:
    """Verify get_organization_by_id returns the organization when user is a member."""
    service = OrganizationService(db_session)
    org = service.create_organization(name="CERT-FR", creator_id=user_a.id)

    fetched = service.get_organization_by_id(org.id, user_id=user_a.id)
    assert fetched.id == org.id
    assert fetched.name == "CERT-FR"


def test_get_organization_by_id_zero_leak_non_member(
    db_session: Session, user_a: User, user_b: User
) -> None:
    """Verify non-member cannot retrieve org (Zero Leak -> OrganizationNotFoundException)."""
    service = OrganizationService(db_session)
    org = service.create_organization(name="Secret Org", creator_id=user_a.id)

    with pytest.raises(OrganizationNotFoundException):
        service.get_organization_by_id(org.id, user_id=user_b.id)


def test_get_organization_by_id_non_existent(db_session: Session, user_a: User) -> None:
    """Verify non-existent organization raises OrganizationNotFoundException."""
    service = OrganizationService(db_session)
    with pytest.raises(OrganizationNotFoundException):
        service.get_organization_by_id(uuid.uuid4(), user_id=user_a.id)


def test_list_user_organizations_pagination(
    db_session: Session, user_a: User, user_b: User
) -> None:
    """Verify list_user_organizations returns only user's orgs with pagination."""
    service = OrganizationService(db_session)
    org1 = service.create_organization("Org 1", creator_id=user_a.id)
    org2 = service.create_organization("Org 2", creator_id=user_a.id)
    service.create_organization("Org Other", creator_id=user_b.id)

    items, total = service.list_user_organizations(user_id=user_a.id, limit=1, offset=0)
    assert total == 2
    assert len(items) == 1

    items_page_2, total_2 = service.list_user_organizations(user_id=user_a.id, limit=1, offset=1)
    assert total_2 == 2
    assert len(items_page_2) == 1
    assert {items[0].id, items_page_2[0].id} == {org1.id, org2.id}


def test_add_member_nominal(db_session: Session, user_a: User, user_b: User) -> None:
    """Verify adding a member succeeds and email is properly resolved."""
    service = OrganizationService(db_session)
    org = service.create_organization("SOC Lab", creator_id=user_a.id)

    membership = service.add_member(org_id=org.id, user_id=user_b.id, role=MembershipRole.ANALYST)
    assert membership.organization_id == org.id
    assert membership.user_id == user_b.id
    assert membership.role == "analyst"
    assert membership.email == user_b.email


def test_add_member_unknown_organization(db_session: Session, user_b: User) -> None:
    """Verify adding member to non-existent organization raises OrganizationNotFoundException."""
    service = OrganizationService(db_session)
    with pytest.raises(OrganizationNotFoundException):
        service.add_member(org_id=uuid.uuid4(), user_id=user_b.id, role=MembershipRole.ANALYST)


def test_add_member_unknown_user(db_session: Session, user_a: User) -> None:
    """Verify adding non-existent user raises UserNotFoundException."""
    service = OrganizationService(db_session)
    org = service.create_organization("SOC Lab", creator_id=user_a.id)

    with pytest.raises(UserNotFoundException):
        service.add_member(org_id=org.id, user_id=uuid.uuid4(), role=MembershipRole.ANALYST)


def test_add_member_inactive_user_raises_user_not_found(
    db_session: Session, user_a: User, user_b: User
) -> None:
    """Verify adding an inactive user raises UserNotFoundException."""
    service = OrganizationService(db_session)
    org = service.create_organization("SOC Lab", creator_id=user_a.id)
    user_b.is_active = False
    db_session.commit()

    with pytest.raises(UserNotFoundException):
        service.add_member(org_id=org.id, user_id=user_b.id, role=MembershipRole.ANALYST)


def test_add_member_already_exists(db_session: Session, user_a: User, user_b: User) -> None:
    """Verify adding an already existing member raises MemberAlreadyExistsException."""
    service = OrganizationService(db_session)
    org = service.create_organization("SOC Lab", creator_id=user_a.id)
    service.add_member(org_id=org.id, user_id=user_b.id, role=MembershipRole.ANALYST)

    with pytest.raises(MemberAlreadyExistsException):
        service.add_member(org_id=org.id, user_id=user_b.id, role=MembershipRole.VIEWER)


def test_update_member_role_nominal(db_session: Session, user_a: User, user_b: User) -> None:
    """Verify updating a member's role succeeds."""
    service = OrganizationService(db_session)
    org = service.create_organization("SOC Lab", creator_id=user_a.id)
    service.add_member(org_id=org.id, user_id=user_b.id, role=MembershipRole.ANALYST)

    updated = service.update_member_role(
        org_id=org.id, target_user_id=user_b.id, new_role=MembershipRole.INVESTIGATOR
    )
    assert updated.role == "investigator"
    assert updated.email == user_b.email


def test_update_member_role_unknown_member(db_session: Session, user_a: User, user_b: User) -> None:
    """Verify updating role of non-member raises MemberNotFoundException."""
    service = OrganizationService(db_session)
    org = service.create_organization("SOC Lab", creator_id=user_a.id)

    with pytest.raises(MemberNotFoundException):
        service.update_member_role(
            org_id=org.id, target_user_id=user_b.id, new_role=MembershipRole.INVESTIGATOR
        )


def test_update_member_role_cannot_demote_last_admin(db_session: Session, user_a: User) -> None:
    """Verify demoting the only admin raises CannotRemoveLastAdminException."""
    service = OrganizationService(db_session)
    org = service.create_organization("SOC Lab", creator_id=user_a.id)

    with pytest.raises(CannotRemoveLastAdminException):
        service.update_member_role(
            org_id=org.id, target_user_id=user_a.id, new_role=MembershipRole.ANALYST
        )


def test_update_member_role_can_demote_admin_if_another_exists(
    db_session: Session, user_a: User, user_b: User
) -> None:
    """Verify demoting an admin succeeds if another admin exists."""
    service = OrganizationService(db_session)
    org = service.create_organization("SOC Lab", creator_id=user_a.id)
    service.add_member(org_id=org.id, user_id=user_b.id, role=MembershipRole.ADMIN)

    updated = service.update_member_role(
        org_id=org.id, target_user_id=user_a.id, new_role=MembershipRole.ANALYST
    )
    assert updated.role == "analyst"


def test_remove_member_nominal(db_session: Session, user_a: User, user_b: User) -> None:
    """Verify removing a member succeeds."""
    service = OrganizationService(db_session)
    org = service.create_organization("SOC Lab", creator_id=user_a.id)
    service.add_member(org_id=org.id, user_id=user_b.id, role=MembershipRole.ANALYST)

    service.remove_member(org_id=org.id, target_user_id=user_b.id)
    members, total = service.list_members(org.id)
    assert total == 1
    assert members[0].user_id == user_a.id


def test_remove_member_unknown_member(db_session: Session, user_a: User, user_b: User) -> None:
    """Verify removing non-member raises MemberNotFoundException."""
    service = OrganizationService(db_session)
    org = service.create_organization("SOC Lab", creator_id=user_a.id)

    with pytest.raises(MemberNotFoundException):
        service.remove_member(org_id=org.id, target_user_id=user_b.id)


def test_remove_member_cannot_remove_last_active_admin_even_if_inactive_exists(
    db_session: Session, user_a: User, user_b: User
) -> None:
    """Verify cannot remove only active admin even if an inactive admin exists."""
    service = OrganizationService(db_session)
    org = service.create_organization("SOC Lab", creator_id=user_a.id)
    service.add_member(org.id, user_b.id, role=MembershipRole.ADMIN)

    # Deactivate user_b
    user_b.is_active = False
    db_session.commit()

    # user_a is now the only active admin -> removing user_a must fail
    with pytest.raises(CannotRemoveLastAdminException):
        service.remove_member(org.id, user_a.id)


def test_remove_member_can_remove_admin_if_another_exists(
    db_session: Session, user_a: User, user_b: User
) -> None:
    """Verify removing an admin succeeds if another admin exists."""
    service = OrganizationService(db_session)
    org = service.create_organization("SOC Lab", creator_id=user_a.id)
    service.add_member(org_id=org.id, user_id=user_b.id, role=MembershipRole.ADMIN)

    service.remove_member(org_id=org.id, target_user_id=user_a.id)
    members, total = service.list_members(org.id)
    assert total == 1
    assert members[0].user_id == user_b.id
