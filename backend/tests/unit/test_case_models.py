"""Unit tests for Case ORM model, relationships, constraints, and cascades."""

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.auth.models import Organization, User
from iryx.cases.models import Case, CaseStatus
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


def test_case_status_enum_values() -> None:
    """Verify CaseStatus enum defines all required operational statuses."""
    assert CaseStatus.OPEN == "open"
    assert CaseStatus.IN_PROGRESS == "in_progress"
    assert CaseStatus.REVIEW == "review"
    assert CaseStatus.CLOSED == "closed"
    assert len(CaseStatus) == 4


def test_case_model_creation_and_defaults(db_session: Session) -> None:
    """Verify nominal creation of Case, default status, UUID assignment, and repr."""
    org = Organization(name="SOC CERT")
    user = User(email="analyst@soc.iryx", hashed_password="hashed_pw")
    db_session.add_all([org, user])
    db_session.commit()

    case = Case(
        organization_id=org.id,
        title="Compromission Ransomware",
        description="Investigation sur un chiffrement massif.",
        created_by=user.id,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    assert isinstance(case.id, uuid.UUID)
    assert case.organization_id == org.id
    assert case.title == "Compromission Ransomware"
    assert case.description == "Investigation sur un chiffrement massif."
    assert case.status == CaseStatus.OPEN
    assert case.created_by == user.id
    assert case.created_at is not None
    assert case.updated_at is not None
    assert "Compromission Ransomware" in repr(case)
    assert str(case.id) in repr(case)
    assert "open" in repr(case)


def test_case_relationships(db_session: Session) -> None:
    """Verify bidirectional ORM relationships between Organization, User, and Case."""
    org = Organization(name="CERT Alpha")
    user = User(email="lead@cert.iryx", hashed_password="hashed_pw")
    db_session.add_all([org, user])
    db_session.commit()

    case = Case(
        organization_id=org.id,
        title="Exfiltration DNS",
        created_by=user.id,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(org)
    db_session.refresh(case)

    assert case.organization == org
    assert case.creator == user
    assert case in org.cases
    assert len(org.cases) == 1


def test_case_cascade_delete_on_organization_removal(db_session: Session) -> None:
    """Verify that deleting an organization cascades and removes its associated cases."""
    org = Organization(name="Org to Delete")
    db_session.add(org)
    db_session.commit()

    case = Case(
        organization_id=org.id,
        title="Dossier Éphémère",
    )
    db_session.add(case)
    db_session.commit()
    case_id = case.id

    # Delete organization
    db_session.delete(org)
    db_session.commit()

    # Case must no longer exist
    retrieved = db_session.get(Case, case_id)
    assert retrieved is None


def test_case_created_by_set_null_on_user_removal(db_session: Session) -> None:
    """Verify that deleting the creator user preserves the Case and sets created_by to NULL."""
    org = Organization(name="Org Persistent")
    user = User(email="investigator@soc.iryx", hashed_password="hashed_pw")
    db_session.add_all([org, user])
    db_session.commit()

    case = Case(
        organization_id=org.id,
        title="Dossier Durable",
        created_by=user.id,
    )
    db_session.add(case)
    db_session.commit()
    case_id = case.id

    # Delete user
    db_session.delete(user)
    db_session.commit()

    # Case still exists, created_by is None
    refreshed_case = db_session.get(Case, case_id)
    assert refreshed_case is not None
    assert refreshed_case.created_by is None
    assert refreshed_case.title == "Dossier Durable"


def test_case_status_check_constraint_violation(db_session: Session) -> None:
    """Verify CheckConstraint rejects unapproved status strings."""
    org = Organization(name="Check Org")
    db_session.add(org)
    db_session.commit()

    # Using invalid status directly
    invalid_case = Case(
        organization_id=org.id,
        title="Status Invalide",
        status="non_existent_status",
    )
    db_session.add(invalid_case)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
