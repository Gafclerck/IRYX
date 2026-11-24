"""Unit tests for Evidence and IngestionRun ORM models, relationships, cascades, and constraints."""

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.auth.models import Organization, User
from iryx.cases.models import Case
from iryx.db.base import Base
from iryx.evidence.models import Evidence, IngestionRun, IngestionStatus


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


def test_ingestion_status_enum_values() -> None:
    """Verify IngestionStatus enum defines all operational statuses."""
    assert IngestionStatus.PENDING == "pending"
    assert IngestionStatus.PROCESSING == "processing"
    assert IngestionStatus.COMPLETED == "completed"
    assert IngestionStatus.FAILED == "failed"
    assert len(IngestionStatus) == 4


def test_evidence_model_creation_and_defaults(db_session: Session) -> None:
    """Verify nominal creation of Evidence, null defaults for sha256/detected_type, and repr."""
    org = Organization(name="CERT Beta")
    user = User(email="analyst@iryx.local", hashed_password="hashed_pw")
    db_session.add_all([org, user])
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Alpha")
    db_session.add(case)
    db_session.commit()

    evidence = Evidence(
        case_id=case.id,
        original_name="memdump.raw",
        file_size=4294967296,
        imported_by=user.id,
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)

    assert isinstance(evidence.id, uuid.UUID)
    assert evidence.case_id == case.id
    assert evidence.original_name == "memdump.raw"
    assert evidence.file_size == 4294967296
    assert evidence.sha256 is None
    assert evidence.detected_type is None
    assert evidence.imported_by == user.id
    assert evidence.created_at is not None
    assert "memdump.raw" in repr(evidence)
    assert str(evidence.id) in repr(evidence)


def test_ingestion_run_model_creation_and_defaults(db_session: Session) -> None:
    """Verify nominal creation of IngestionRun, defaults (pending, 0 progress), and repr."""
    org = Organization(name="CERT Gamma")
    case = Case(organization_id=org.id, title="Affaire Gamma")
    db_session.add_all([org, case])
    db_session.commit()

    evidence = Evidence(
        case_id=case.id,
        original_name="disk.dd",
        file_size=1048576,
    )
    db_session.add(evidence)
    db_session.commit()

    run = IngestionRun(evidence_id=evidence.id)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    assert isinstance(run.id, uuid.UUID)
    assert run.evidence_id == evidence.id
    assert run.status == IngestionStatus.PENDING
    assert run.progress == 0
    assert run.error_message is None
    assert run.started_at is not None
    assert run.completed_at is None
    assert "pending" in repr(run)
    assert str(run.id) in repr(run)


def test_evidence_case_and_run_bidirectional_relationships(db_session: Session) -> None:
    """Verify bidirectional ORM navigation between Case, Evidence, User, and IngestionRun."""
    org = Organization(name="CERT Delta")
    user = User(email="investigator@iryx.local", hashed_password="hashed_pw")
    case = Case(organization_id=org.id, title="Affaire Delta", created_by=user.id)
    db_session.add_all([org, user, case])
    db_session.commit()

    evidence = Evidence(
        case_id=case.id,
        original_name="network.pcap",
        file_size=2048,
        imported_by=user.id,
    )
    db_session.add(evidence)
    db_session.commit()

    run = IngestionRun(
        evidence_id=evidence.id,
        status=IngestionStatus.PROCESSING,
        progress=50,
    )
    db_session.add(run)
    db_session.commit()

    db_session.refresh(case)
    db_session.refresh(evidence)
    db_session.refresh(run)

    assert evidence in case.evidences
    assert evidence.case == case
    assert evidence.importer == user
    assert run in evidence.ingestion_runs
    assert run.evidence == evidence


def test_cascade_delete_case_removes_evidence_and_ingestion_runs(db_session: Session) -> None:
    """Verify deleting a Case cascades and deletes all associated Evidences and IngestionRuns."""
    org = Organization(name="Org Cascade")
    case = Case(organization_id=org.id, title="Case Cascade")
    db_session.add_all([org, case])
    db_session.commit()

    evidence = Evidence(case_id=case.id, original_name="sample.evtx", file_size=512)
    db_session.add(evidence)
    db_session.commit()

    run = IngestionRun(evidence_id=evidence.id)
    db_session.add(run)
    db_session.commit()

    evidence_id = evidence.id
    run_id = run.id

    # Delete Case
    db_session.delete(case)
    db_session.commit()

    # Evidence and IngestionRun must be deleted
    assert db_session.get(Evidence, evidence_id) is None
    assert db_session.get(IngestionRun, run_id) is None


def test_cascade_delete_evidence_removes_ingestion_runs(db_session: Session) -> None:
    """Verify that deleting an Evidence cascades and deletes its associated IngestionRuns."""
    org = Organization(name="Org Evidence Cascade")
    case = Case(organization_id=org.id, title="Case Evidence Cascade")
    db_session.add_all([org, case])
    db_session.commit()

    evidence = Evidence(case_id=case.id, original_name="sample2.evtx", file_size=1024)
    db_session.add(evidence)
    db_session.commit()

    run1 = IngestionRun(evidence_id=evidence.id, progress=10)
    run2 = IngestionRun(evidence_id=evidence.id, progress=20)
    db_session.add_all([run1, run2])
    db_session.commit()

    run1_id, run2_id = run1.id, run2.id

    # Delete Evidence
    db_session.delete(evidence)
    db_session.commit()

    assert db_session.get(IngestionRun, run1_id) is None
    assert db_session.get(IngestionRun, run2_id) is None


def test_imported_by_set_null_on_user_deletion(db_session: Session) -> None:
    """Verify deleting importing user sets imported_by to NULL without deleting Evidence."""
    org = Organization(name="Org User SetNull")
    user = User(email="uploader@iryx.local", hashed_password="hashed_pw")
    case = Case(organization_id=org.id, title="Case SetNull")
    db_session.add_all([org, user, case])
    db_session.commit()

    evidence = Evidence(
        case_id=case.id,
        original_name="system.img",
        file_size=8192,
        imported_by=user.id,
    )
    db_session.add(evidence)
    db_session.commit()
    evidence_id = evidence.id

    # Delete user
    db_session.delete(user)
    db_session.commit()

    refreshed_evidence = db_session.get(Evidence, evidence_id)
    assert refreshed_evidence is not None
    assert refreshed_evidence.imported_by is None
    assert refreshed_evidence.original_name == "system.img"


def test_evidence_case_foreign_key_violation(db_session: Session) -> None:
    """Verify that creating Evidence with non-existent case_id raises IntegrityError."""
    fake_case_id = uuid.uuid4()
    evidence = Evidence(
        case_id=fake_case_id,
        original_name="orphan.bin",
        file_size=100,
    )
    db_session.add(evidence)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_ingestion_run_evidence_foreign_key_violation(db_session: Session) -> None:
    """Verify that creating IngestionRun with non-existent evidence_id raises IntegrityError."""
    fake_evidence_id = uuid.uuid4()
    run = IngestionRun(evidence_id=fake_evidence_id)
    db_session.add(run)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_ingestion_run_status_check_constraint_violation(db_session: Session) -> None:
    """Verify CheckConstraint rejects unapproved status strings."""
    org = Organization(name="Org Ingestion Check")
    case = Case(organization_id=org.id, title="Case Ingestion Check")
    db_session.add_all([org, case])
    db_session.commit()

    evidence = Evidence(case_id=case.id, original_name="file.bin", file_size=50)
    db_session.add(evidence)
    db_session.commit()

    invalid_run = IngestionRun(
        evidence_id=evidence.id,
        status="invalid_status",
    )
    db_session.add(invalid_run)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize("invalid_progress", [-1, 101, -50, 150])
def test_ingestion_run_progress_range_constraint_violation(
    db_session: Session, invalid_progress: int
) -> None:
    """Verify CheckConstraint rejects progress values outside [0, 100]."""
    org = Organization(name="Org Progress Check")
    case = Case(organization_id=org.id, title="Case Progress Check")
    db_session.add_all([org, case])
    db_session.commit()

    evidence = Evidence(case_id=case.id, original_name="file2.bin", file_size=50)
    db_session.add(evidence)
    db_session.commit()

    invalid_run = IngestionRun(
        evidence_id=evidence.id,
        progress=invalid_progress,
    )
    db_session.add(invalid_run)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_evidence_file_size_non_negative_constraint(db_session: Session) -> None:
    """Verify CheckConstraint rejects negative file_size values on Evidence."""
    org = Organization(name="Org FileSize Check")
    case = Case(organization_id=org.id, title="Case FileSize Check")
    db_session.add_all([org, case])
    db_session.commit()

    invalid_evidence = Evidence(
        case_id=case.id,
        original_name="negative_size.bin",
        file_size=-1,
    )
    db_session.add(invalid_evidence)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_configure_mappers_succeeds_without_unmapped_class_error() -> None:
    """Verify SQLAlchemy configure_mappers succeeds cleanly with mutual relationship imports."""
    from sqlalchemy.orm import configure_mappers
    configure_mappers()

