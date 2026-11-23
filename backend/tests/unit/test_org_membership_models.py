"""Unit tests for Organization and Membership ORM models, constraints, and cascades."""

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.auth.models import Membership, MembershipRole, Organization, User
from iryx.db.base import Base


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an in-memory SQLite session with foreign key enforcement."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_organization_model_nominal(db_session: Session) -> None:
    """Verify Organization model creation, defaults, UUID and string representation."""
    org = Organization(name="CERT Interne")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)

    assert isinstance(org.id, uuid.UUID)
    assert org.name == "CERT Interne"
    assert org.created_at is not None
    assert org.updated_at is not None
    assert "CERT Interne" in repr(org)
    assert str(org.id) in repr(org)


def test_membership_model_nominal(db_session: Session) -> None:
    """Verify Membership creation, relation linking, and string representation."""
    org = Organization(name="SOC Team")
    user = User(email="analyst@iryx.io", hashed_password="hashed_secret_pw")
    db_session.add_all([org, user])
    db_session.commit()

    membership = Membership(
        organization_id=org.id,
        user_id=user.id,
        role=MembershipRole.ANALYST,
    )
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)

    assert isinstance(membership.id, uuid.UUID)
    assert membership.organization_id == org.id
    assert membership.user_id == user.id
    assert membership.role == "analyst"
    assert membership.created_at is not None
    assert membership.organization == org
    assert membership.user == user
    assert membership in org.memberships
    assert membership in user.memberships
    assert "analyst" in repr(membership)
    assert str(org.id) in repr(membership)


def test_membership_all_roles_persisted(db_session: Session) -> None:
    """Verify all 4 RBAC roles can be persisted as Membership."""
    org = Organization(name="Multi-Role Org")
    db_session.add(org)
    db_session.commit()

    roles = [
        MembershipRole.ADMIN,
        MembershipRole.ANALYST,
        MembershipRole.INVESTIGATOR,
        MembershipRole.VIEWER,
    ]

    for role in roles:
        user = User(email=f"{role.value}@iryx.io", hashed_password="hashed_secret_pw")
        db_session.add(user)
        db_session.commit()

        membership = Membership(organization_id=org.id, user_id=user.id, role=role)
        db_session.add(membership)
        db_session.commit()
        assert membership.role == role.value


def test_membership_duplicate_org_user_rejected(db_session: Session) -> None:
    """Verify composite unique constraint blocks duplicate org and user memberships."""
    org = Organization(name="Duplicate Test Org")
    user = User(email="dup@iryx.io", hashed_password="hashed_secret_pw")
    db_session.add_all([org, user])
    db_session.commit()

    m1 = Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.ADMIN)
    db_session.add(m1)
    db_session.commit()

    m2 = Membership(organization_id=org.id, user_id=user.id, role=MembershipRole.VIEWER)
    db_session.add(m2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_membership_invalid_role_check_constraint_rejected(db_session: Session) -> None:
    """Verify CHECK constraint rejects invalid roles at SQL database level."""
    org = Organization(name="Check Test Org")
    user = User(email="check@iryx.io", hashed_password="hashed_secret_pw")
    db_session.add_all([org, user])
    db_session.commit()

    invalid_membership = Membership(
        organization_id=org.id,
        user_id=user.id,
        role="superuser",
    )
    db_session.add(invalid_membership)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_membership_cascade_delete_organization(db_session: Session) -> None:
    """Verify deleting an Organization cascade deletes its Memberships without orphans."""
    org = Organization(name="Org To Delete")
    u1 = User(email="u1@iryx.io", hashed_password="pw1")
    u2 = User(email="u2@iryx.io", hashed_password="pw2")
    db_session.add_all([org, u1, u2])
    db_session.commit()

    m1 = Membership(organization_id=org.id, user_id=u1.id, role=MembershipRole.ADMIN)
    m2 = Membership(organization_id=org.id, user_id=u2.id, role=MembershipRole.ANALYST)
    db_session.add_all([m1, m2])
    db_session.commit()

    assert len(db_session.query(Membership).filter_by(organization_id=org.id).all()) == 2

    db_session.delete(org)
    db_session.commit()

    # Memberships should be gone
    assert len(db_session.query(Membership).filter_by(organization_id=org.id).all()) == 0
    # Users remain intact
    assert db_session.get(User, u1.id) is not None
    assert db_session.get(User, u2.id) is not None


def test_membership_cascade_delete_user(db_session: Session) -> None:
    """Verify deleting a User cascade deletes their Memberships without orphans."""
    org1 = Organization(name="Org 1")
    org2 = Organization(name="Org 2")
    user = User(email="user_to_delete@iryx.io", hashed_password="pw")
    db_session.add_all([org1, org2, user])
    db_session.commit()

    m1 = Membership(organization_id=org1.id, user_id=user.id, role=MembershipRole.INVESTIGATOR)
    m2 = Membership(organization_id=org2.id, user_id=user.id, role=MembershipRole.VIEWER)
    db_session.add_all([m1, m2])
    db_session.commit()

    assert len(db_session.query(Membership).filter_by(user_id=user.id).all()) == 2

    db_session.delete(user)
    db_session.commit()

    # Memberships should be gone
    assert len(db_session.query(Membership).filter_by(user_id=user.id).all()) == 0
    # Organizations remain intact
    assert db_session.get(Organization, org1.id) is not None
    assert db_session.get(Organization, org2.id) is not None


def test_membership_foreign_key_missing_org_rejected(db_session: Session) -> None:
    """Verify inserting Membership with non-existent organization_id fails FK constraint."""
    user = User(email="no_org@iryx.io", hashed_password="pw")
    db_session.add(user)
    db_session.commit()

    membership = Membership(
        organization_id=uuid.uuid4(),
        user_id=user.id,
        role=MembershipRole.ADMIN,
    )
    db_session.add(membership)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_membership_foreign_key_missing_user_rejected(db_session: Session) -> None:
    """Verify inserting Membership with non-existent user_id fails FK constraint."""
    org = Organization(name="No User Org")
    db_session.add(org)
    db_session.commit()

    membership = Membership(
        organization_id=org.id,
        user_id=uuid.uuid4(),
        role=MembershipRole.ADMIN,
    )
    db_session.add(membership)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
