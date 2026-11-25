"""Unit tests for Finding ORM model, UUIDList TypeDecorator, and Pydantic v2 schemas."""

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.analytics.models import (
    Finding,
    FindingConfidence,
    FindingSeverity,
    FindingStatus,
    FindingType,
    UUIDList,
)
from iryx.analytics.schemas import (
    FindingCreate,
    FindingListResponse,
    FindingOut,
    FindingReview,
    FindingUpdate,
)
from iryx.auth.models import Organization, User
from iryx.cases.models import Case
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


# =========================================================================
# 1. Pydantic v2 Schemas Tests
# =========================================================================


def test_finding_create_minimal_valid() -> None:
    """Verify minimal valid FindingCreate populates appropriate defaults."""
    schema = FindingCreate(title="Suspicious Scheduled Task", severity=FindingSeverity.HIGH)
    assert schema.title == "Suspicious Scheduled Task"
    assert schema.severity == FindingSeverity.HIGH
    assert schema.confidence == FindingConfidence.MEDIUM
    assert schema.finding_type == FindingType.FACT
    assert schema.observation_refs == []
    assert schema.tool_execution_refs == []


def test_finding_create_full_valid() -> None:
    """Verify full FindingCreate payload preserves all specified attributes."""
    obs_id = uuid.uuid4()
    tool_id = uuid.uuid4()
    schema = FindingCreate(
        title="Cobalt Strike Beacon Injected",
        severity=FindingSeverity.CRITICAL,
        confidence=FindingConfidence.HIGH,
        finding_type=FindingType.INFERENCE,
        observation_refs=[obs_id],
        tool_execution_refs=[tool_id],
    )
    assert schema.title == "Cobalt Strike Beacon Injected"
    assert schema.severity == FindingSeverity.CRITICAL
    assert schema.confidence == FindingConfidence.HIGH
    assert schema.finding_type == FindingType.INFERENCE
    assert schema.observation_refs == [obs_id]
    assert schema.tool_execution_refs == [tool_id]


def test_finding_create_invalid_severity_raises_422() -> None:
    """Verify invalid severity triggers Pydantic ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        FindingCreate(title="Test", severity="extreme")  # type: ignore[arg-type]
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("severity",) for err in errors)


def test_finding_create_invalid_confidence_raises_422() -> None:
    """Verify invalid confidence triggers Pydantic ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        FindingCreate(title="Test", severity=FindingSeverity.LOW, confidence="certain")  # type: ignore[arg-type]
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("confidence",) for err in errors)


def test_finding_create_invalid_finding_type_raises_422() -> None:
    """Verify invalid finding_type triggers Pydantic ValidationError."""
    with pytest.raises(ValidationError) as exc_info:
        FindingCreate(title="Test", severity=FindingSeverity.LOW, finding_type="speculation")  # type: ignore[arg-type]
    errors = exc_info.value.errors()
    assert any(err["loc"] == ("finding_type",) for err in errors)


def test_finding_create_empty_title_raises_422() -> None:
    """Verify whitespace or empty title triggers ValidationError."""
    with pytest.raises(ValidationError):
        FindingCreate(title="", severity=FindingSeverity.LOW)

    with pytest.raises(ValidationError):
        FindingCreate(title="   ", severity=FindingSeverity.LOW)


def test_finding_create_overly_long_title_raises_422() -> None:
    """Verify title exceeding 255 chars triggers ValidationError."""
    with pytest.raises(ValidationError):
        FindingCreate(title="x" * 256, severity=FindingSeverity.LOW)


def test_finding_update_partial_valid() -> None:
    """Verify FindingUpdate accepts partial fields and trims title."""
    update = FindingUpdate(
        title="  Updated Finding  ",
        status=FindingStatus.VALIDATED,
        severity=FindingSeverity.CRITICAL,
    )
    assert update.title == "Updated Finding"
    assert update.status == FindingStatus.VALIDATED
    assert update.severity == FindingSeverity.CRITICAL
    assert update.confidence is None


def test_finding_update_empty_title_raises_422() -> None:
    """Verify whitespace-only updated title triggers ValidationError."""
    with pytest.raises(ValidationError):
        FindingUpdate(title="   ")


def test_finding_review_schema() -> None:
    """Verify FindingReview schema accepts validate/reject with optional adjustments."""
    rev_val = FindingReview(action="validate", severity=FindingSeverity.HIGH)
    assert rev_val.action == "validate"
    assert rev_val.severity == FindingSeverity.HIGH
    assert rev_val.confidence is None

    rev_rej = FindingReview(action="reject")
    assert rev_rej.action == "reject"

    with pytest.raises(ValidationError):
        FindingReview(action="postpone")  # type: ignore[arg-type]


def test_finding_list_response_population() -> None:
    """Verify FindingListResponse populates total_items and computes has_more."""
    finding_id = uuid.uuid4()
    case_id = uuid.uuid4()
    out = FindingOut(
        id=finding_id,
        case_id=case_id,
        title="Constat validé",
        severity=FindingSeverity.HIGH,
        confidence=FindingConfidence.HIGH,
        finding_type=FindingType.FACT,
        status=FindingStatus.VALIDATED,
        observation_refs=[],
        tool_execution_refs=[],
        created_at=datetime.now(UTC),
    )

    resp = FindingListResponse(items=[out], total=10, limit=5, offset=0, has_more=True)
    assert resp.total_items == 10
    assert resp.total == 10
    assert resp.has_more is True


# =========================================================================
# 2. UUIDList TypeDecorator Tests
# =========================================================================


def test_uuid_list_type_decorator_pg_sqlite() -> None:
    """Verify UUIDList process_bind_param and process_result_value on Postgres and SQLite."""
    decorator = UUIDList()
    pg_dialect = postgresql.dialect()
    sqlite_dialect = sqlite.dialect()

    u1 = uuid.uuid4()
    u2 = uuid.uuid4()

    # PostgreSQL bind and result
    pg_bound = decorator.process_bind_param([u1, str(u2)], pg_dialect)
    assert pg_bound == [u1, u2]
    assert decorator.process_result_value(pg_bound, pg_dialect) == [u1, u2]

    # SQLite bind and result
    sqlite_bound = decorator.process_bind_param([u1, u2], sqlite_dialect)
    assert sqlite_bound == [str(u1), str(u2)]
    # Result as list of strings
    assert decorator.process_result_value(sqlite_bound, sqlite_dialect) == [u1, u2]
    # Result as JSON string
    json_str = json.dumps([str(u1), str(u2)])
    assert decorator.process_result_value(json_str, sqlite_dialect) == [u1, u2]
    # Test scalar bind normalization
    scalar_uuid = uuid.uuid4()
    assert decorator.process_bind_param(scalar_uuid, pg_dialect) == [scalar_uuid]
    assert decorator.process_bind_param(str(scalar_uuid), sqlite_dialect) == [str(scalar_uuid)]

    # Result as None or empty
    assert decorator.process_result_value(None, sqlite_dialect) == []
    assert decorator.process_result_value("invalid json", sqlite_dialect) == []


# =========================================================================
# 3. SQLAlchemy ORM Model Tests
# =========================================================================


def test_finding_init_defaults() -> None:
    """Verify Finding.__init__ populates defaults for all required attributes."""
    f = Finding(title="Defaults Test")
    assert f.severity == FindingSeverity.LOW
    assert f.confidence == FindingConfidence.MEDIUM
    assert f.finding_type == FindingType.FACT
    assert f.status == FindingStatus.PROPOSED
    assert f.observation_refs == []
    assert f.tool_execution_refs == []


def test_finding_orm_nominal_creation(db_session: Session) -> None:
    """Verify nominal Finding persistence, relationships, and default proposed status."""
    org = Organization(name="CERT Beta")
    db_session.add(org)
    db_session.commit()

    user = User(email="analyst@soc.iryx", hashed_password="argon2_hash_placeholder")
    db_session.add(user)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire APT29", created_by=user.id)
    db_session.add(case)
    db_session.commit()

    obs_id = uuid.uuid4()
    tool_id = uuid.uuid4()

    finding = Finding(
        case_id=case.id,
        title="Persistance détectée via clé Run",
        severity=FindingSeverity.HIGH,
        confidence=FindingConfidence.HIGH,
        finding_type=FindingType.FACT,
        observation_refs=[obs_id],
        tool_execution_refs=[tool_id],
        created_by=user.id,
    )
    db_session.add(finding)
    db_session.commit()

    # Query back
    fetched = db_session.get(Finding, finding.id)
    assert fetched is not None
    assert fetched.case_id == case.id
    assert fetched.title == "Persistance détectée via clé Run"
    assert fetched.severity == FindingSeverity.HIGH
    assert fetched.confidence == FindingConfidence.HIGH
    assert fetched.finding_type == FindingType.FACT
    assert fetched.status == FindingStatus.PROPOSED
    assert fetched.observation_refs == [obs_id]
    assert fetched.tool_execution_refs == [tool_id]
    assert fetched.created_by == user.id
    assert isinstance(fetched.created_at, datetime)
    assert "Finding id=" in repr(fetched)

    # Test bidirectional relationship with Case
    assert finding in case.findings


def test_finding_orm_check_constraints(db_session: Session) -> None:
    """Verify DB check constraints on severity, confidence, finding_type, status."""
    org = Organization(name="CERT Alpha")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Test Dossier")
    db_session.add(case)
    db_session.commit()

    # Invalid severity
    f_bad_sev = Finding(case_id=case.id, title="Bad Sev", severity="fatal")  # type: ignore[arg-type]
    db_session.add(f_bad_sev)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Invalid status
    f_bad_status = Finding(case_id=case.id, title="Bad Status", status="unknown")  # type: ignore[arg-type]
    db_session.add(f_bad_status)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_finding_cascade_delete_with_case(db_session: Session) -> None:
    """Verify deleting a case deletes all associated findings in cascade."""
    org = Organization(name="CERT Gamma")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire à supprimer")
    db_session.add(case)
    db_session.commit()

    finding = Finding(case_id=case.id, title="Constat associé")
    db_session.add(finding)
    db_session.commit()

    f_id = finding.id
    db_session.delete(case)
    db_session.commit()

    assert db_session.get(Finding, f_id) is None
