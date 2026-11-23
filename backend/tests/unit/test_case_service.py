"""Unit tests for CaseService business logic and status transition matrix."""

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.auth.models import Membership, MembershipRole, Organization, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.models import CaseStatus
from iryx.cases.services import VALID_STATUS_TRANSITIONS, CaseService
from iryx.core.exceptions import (
    CaseNotFoundException,
    InsufficientPermissionsException,
    InvalidStatusTransitionException,
    OrganizationNotFoundException,
    ValidationException,
)
from iryx.db.base import Base


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
def test_org(db_session: Session) -> Organization:
    """Create test organization."""
    org = Organization(name="SOC Investigation Group")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def investigator_user(db_session: Session, test_org: Organization) -> User:
    """Create investigator user with active investigator membership."""
    user = UserService(db_session).create_user(
        UserCreate(email="investigator@soc.iryx", password="Password123!")
    )
    membership = Membership(
        organization_id=test_org.id,
        user_id=user.id,
        role=MembershipRole.INVESTIGATOR.value,
    )
    db_session.add(membership)
    db_session.commit()
    return user


@pytest.fixture
def viewer_user(db_session: Session, test_org: Organization) -> User:
    """Create viewer user with active viewer membership."""
    user = UserService(db_session).create_user(
        UserCreate(email="viewer@soc.iryx", password="Password123!")
    )
    membership = Membership(
        organization_id=test_org.id,
        user_id=user.id,
        role=MembershipRole.VIEWER.value,
    )
    db_session.add(membership)
    db_session.commit()
    return user


@pytest.fixture
def outsider_user(db_session: Session) -> User:
    """Create user with no organization memberships."""
    return UserService(db_session).create_user(
        UserCreate(email="outsider@soc.iryx", password="Password123!")
    )


def test_valid_status_transitions_matrix_integrity() -> None:
    """Verify that VALID_STATUS_TRANSITIONS matches the specification exactly."""
    assert VALID_STATUS_TRANSITIONS[CaseStatus.OPEN] == {
        CaseStatus.IN_PROGRESS,
        CaseStatus.CLOSED,
    }
    assert VALID_STATUS_TRANSITIONS[CaseStatus.IN_PROGRESS] == {
        CaseStatus.REVIEW,
        CaseStatus.OPEN,
        CaseStatus.CLOSED,
    }
    assert VALID_STATUS_TRANSITIONS[CaseStatus.REVIEW] == {
        CaseStatus.CLOSED,
        CaseStatus.IN_PROGRESS,
    }
    assert VALID_STATUS_TRANSITIONS[CaseStatus.CLOSED] == set()


def test_create_case_nominal(
    db_session: Session, test_org: Organization, investigator_user: User
) -> None:
    """Verify nominal case creation with status open and creator assigned."""
    service = CaseService(db_session)
    case = service.create_case(
        org_id=test_org.id,
        title="  Compromission AD DC01  ",
        description="Tentative de dump LSASS",
        creator_id=investigator_user.id,
    )

    assert case.id is not None
    assert case.organization_id == test_org.id
    assert case.title == "Compromission AD DC01"
    assert case.description == "Tentative de dump LSASS"
    assert case.status == CaseStatus.OPEN
    assert case.created_by == investigator_user.id


def test_create_case_empty_or_whitespace_title_raises_validation_exception(
    db_session: Session, test_org: Organization, investigator_user: User
) -> None:
    """Verify that an empty or whitespace title raises ValidationException."""
    service = CaseService(db_session)
    with pytest.raises(ValidationException):
        service.create_case(
            org_id=test_org.id,
            title="   ",
            description=None,
            creator_id=investigator_user.id,
        )


def test_create_case_title_exceeding_255_raises_validation_exception(
    db_session: Session, test_org: Organization, investigator_user: User
) -> None:
    """Verify that a title longer than 255 chars raises ValidationException."""
    service = CaseService(db_session)
    with pytest.raises(ValidationException):
        service.create_case(
            org_id=test_org.id,
            title="A" * 256,
            description=None,
            creator_id=investigator_user.id,
        )


def test_create_case_unknown_organization_raises_not_found(
    db_session: Session, investigator_user: User
) -> None:
    """Verify that an unknown organization_id raises OrganizationNotFoundException."""
    service = CaseService(db_session)
    with pytest.raises(OrganizationNotFoundException):
        service.create_case(
            org_id=uuid.uuid4(),
            title="Dossier Invalide",
            description=None,
            creator_id=investigator_user.id,
        )


def test_list_cases_pagination(
    db_session: Session, test_org: Organization, investigator_user: User
) -> None:
    """Verify list_cases returns paginated items and accurate total count."""
    service = CaseService(db_session)
    for i in range(5):
        service.create_case(
            org_id=test_org.id,
            title=f"Incident #{i + 1}",
            description=None,
            creator_id=investigator_user.id,
        )

    # Page 1 (limit 2, offset 0)
    items_p1, total = service.list_cases(org_id=test_org.id, limit=2, offset=0)
    assert total == 5
    assert len(items_p1) == 2

    # Page 3 (limit 2, offset 4)
    items_p3, total_p3 = service.list_cases(org_id=test_org.id, limit=2, offset=4)
    assert total_p3 == 5
    assert len(items_p3) == 1

    # Invalid pagination
    with pytest.raises(ValidationException):
        service.list_cases(org_id=test_org.id, limit=0, offset=0)
    with pytest.raises(ValidationException):
        service.list_cases(org_id=test_org.id, limit=10, offset=-1)


def test_get_case_by_id_nominal(
    db_session: Session, test_org: Organization, investigator_user: User
) -> None:
    """Verify get_case_by_id retrieves case for an authorized member."""
    service = CaseService(db_session)
    created = service.create_case(
        org_id=test_org.id,
        title="Dossier Consultation",
        description=None,
        creator_id=investigator_user.id,
    )

    retrieved = service.get_case_by_id(case_id=created.id, user_id=investigator_user.id)
    assert retrieved.id == created.id
    assert retrieved.title == "Dossier Consultation"


def test_get_case_by_id_unknown_raises_case_not_found(
    db_session: Session, investigator_user: User
) -> None:
    """Verify unknown case_id raises CaseNotFoundException."""
    service = CaseService(db_session)
    with pytest.raises(CaseNotFoundException):
        service.get_case_by_id(case_id=uuid.uuid4(), user_id=investigator_user.id)


def test_get_case_by_id_outsider_raises_insufficient_permissions(
    db_session: Session,
    test_org: Organization,
    investigator_user: User,
    outsider_user: User,
) -> None:
    """Verify non-member user cannot access case (Zero Leak)."""
    service = CaseService(db_session)
    case = service.create_case(
        org_id=test_org.id,
        title="Dossier Confidentiel",
        description=None,
        creator_id=investigator_user.id,
    )

    with pytest.raises(InsufficientPermissionsException):
        service.get_case_by_id(case_id=case.id, user_id=outsider_user.id)


def test_update_case_status_nominal_lifecycle(
    db_session: Session, test_org: Organization, investigator_user: User
) -> None:
    """Verify nominal sequence: open -> in_progress -> review -> closed."""
    service = CaseService(db_session)
    case = service.create_case(
        org_id=test_org.id,
        title="Dossier Cycle Complet",
        description=None,
        creator_id=investigator_user.id,
    )
    assert case.status == CaseStatus.OPEN

    # 1. open -> in_progress
    c1 = service.update_case_status(
        case_id=case.id,
        new_status=CaseStatus.IN_PROGRESS,
        user_id=investigator_user.id,
    )
    assert c1.status == CaseStatus.IN_PROGRESS

    # 2. in_progress -> review
    c2 = service.update_case_status(
        case_id=case.id,
        new_status=CaseStatus.REVIEW,
        user_id=investigator_user.id,
    )
    assert c2.status == CaseStatus.REVIEW

    # 3. review -> closed
    c3 = service.update_case_status(
        case_id=case.id,
        new_status=CaseStatus.CLOSED,
        user_id=investigator_user.id,
    )
    assert c3.status == CaseStatus.CLOSED


def test_update_case_status_additional_valid_transitions(
    db_session: Session, test_org: Organization, investigator_user: User
) -> None:
    """Verify valid alternative paths: open -> closed, in_progress -> open, review -> in_prog."""
    service = CaseService(db_session)

    # Path A: open -> closed
    case_a = service.create_case(
        org_id=test_org.id,
        title="Case Direct Close",
        description=None,
        creator_id=investigator_user.id,
    )
    ca = service.update_case_status(case_a.id, CaseStatus.CLOSED, investigator_user.id)
    assert ca.status == CaseStatus.CLOSED

    # Path B: open -> in_progress -> open
    case_b = service.create_case(
        org_id=test_org.id,
        title="Case Reopen to Open",
        description=None,
        creator_id=investigator_user.id,
    )
    service.update_case_status(case_b.id, CaseStatus.IN_PROGRESS, investigator_user.id)
    cb = service.update_case_status(case_b.id, CaseStatus.OPEN, investigator_user.id)
    assert cb.status == CaseStatus.OPEN

    # Path C: open -> in_progress -> review -> in_progress
    case_c = service.create_case(
        org_id=test_org.id,
        title="Case Review to In Progress",
        description=None,
        creator_id=investigator_user.id,
    )
    service.update_case_status(case_c.id, CaseStatus.IN_PROGRESS, investigator_user.id)
    service.update_case_status(case_c.id, CaseStatus.REVIEW, investigator_user.id)
    cc = service.update_case_status(case_c.id, CaseStatus.IN_PROGRESS, investigator_user.id)
    assert cc.status == CaseStatus.IN_PROGRESS


def test_update_case_status_terminal_closed_rejects_all_transitions(
    db_session: Session, test_org: Organization, investigator_user: User
) -> None:
    """Verify closed is a terminal state and cannot transition to any other status."""
    service = CaseService(db_session)
    case = service.create_case(
        org_id=test_org.id,
        title="Dossier Clos",
        description=None,
        creator_id=investigator_user.id,
    )
    service.update_case_status(case.id, CaseStatus.CLOSED, investigator_user.id)

    # Any transition from closed must be rejected
    for target in [CaseStatus.OPEN, CaseStatus.IN_PROGRESS, CaseStatus.REVIEW, CaseStatus.CLOSED]:
        with pytest.raises(InvalidStatusTransitionException) as exc_info:
            service.update_case_status(case.id, target, investigator_user.id)
        assert exc_info.value.code == "INVALID_STATUS_TRANSITION"


def test_update_case_status_illegal_transitions_rejected(
    db_session: Session, test_org: Organization, investigator_user: User
) -> None:
    """Verify unallowed non-adjacent transitions are rejected."""
    service = CaseService(db_session)

    # 1. open -> review is illegal
    case1 = service.create_case(
        org_id=test_org.id,
        title="Test Illegal 1",
        description=None,
        creator_id=investigator_user.id,
    )
    with pytest.raises(InvalidStatusTransitionException):
        service.update_case_status(case1.id, CaseStatus.REVIEW, investigator_user.id)

    # 2. review -> open is illegal
    case2 = service.create_case(
        org_id=test_org.id,
        title="Test Illegal 2",
        description=None,
        creator_id=investigator_user.id,
    )
    service.update_case_status(case2.id, CaseStatus.IN_PROGRESS, investigator_user.id)
    service.update_case_status(case2.id, CaseStatus.REVIEW, investigator_user.id)
    with pytest.raises(InvalidStatusTransitionException):
        service.update_case_status(case2.id, CaseStatus.OPEN, investigator_user.id)

    # 3. same status -> same status is illegal
    with pytest.raises(InvalidStatusTransitionException):
        service.update_case_status(case2.id, CaseStatus.REVIEW, investigator_user.id)


def test_update_case_status_viewer_forbidden(
    db_session: Session,
    test_org: Organization,
    investigator_user: User,
    viewer_user: User,
) -> None:
    """Verify viewer cannot mutate case status."""
    service = CaseService(db_session)
    case = service.create_case(
        org_id=test_org.id,
        title="Case for Viewer Test",
        description=None,
        creator_id=investigator_user.id,
    )

    with pytest.raises(InsufficientPermissionsException):
        service.update_case_status(case.id, CaseStatus.IN_PROGRESS, viewer_user.id)


def test_update_case_status_outsider_forbidden(
    db_session: Session,
    test_org: Organization,
    investigator_user: User,
    outsider_user: User,
) -> None:
    """Verify non-member user cannot mutate case status."""
    service = CaseService(db_session)
    case = service.create_case(
        org_id=test_org.id,
        title="Case for Outsider Test",
        description=None,
        creator_id=investigator_user.id,
    )

    with pytest.raises(InsufficientPermissionsException):
        service.update_case_status(case.id, CaseStatus.IN_PROGRESS, outsider_user.id)
