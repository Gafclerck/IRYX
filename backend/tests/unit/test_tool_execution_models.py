"""Unit tests for ToolExecution and Observation models, relationships, and constraints."""

import uuid
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.analytics.models import Observation
from iryx.auth.models import Organization, User
from iryx.cases.models import Case
from iryx.db.base import Base
from iryx.evidence.models import Evidence
from iryx.gateway.models import ToolExecution, ToolExecutionStatus


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


def test_tool_execution_status_enum_values() -> None:
    """Verify ToolExecutionStatus enum values."""
    assert ToolExecutionStatus.SUCCESS == "success"
    assert ToolExecutionStatus.ERROR == "error"
    assert ToolExecutionStatus.TIMEOUT == "timeout"
    assert len(ToolExecutionStatus) == 3


def test_tool_execution_creation_and_defaults(db_session: Session) -> None:
    """Verify nominal creation of ToolExecution, default values, and repr."""
    org = Organization(name="CERT Delta")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Forensique")
    db_session.add(case)
    db_session.commit()

    execution = ToolExecution(
        case_id=case.id,
        tool_name="hash_sha256",
        tool_version="1.0.0",
        agent_role="Executor",
        parameters={"evidence_id": str(uuid.uuid4())},
        result_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        duration_ms=45,
    )
    db_session.add(execution)
    db_session.commit()
    db_session.refresh(execution)

    assert isinstance(execution.id, uuid.UUID)
    assert execution.case_id == case.id
    assert execution.tool_name == "hash_sha256"
    assert execution.tool_version == "1.0.0"
    assert execution.agent_role == "Executor"
    assert execution.status == ToolExecutionStatus.SUCCESS
    assert execution.duration_ms == 45
    assert execution.error_message is None
    assert execution.created_at is not None
    assert "hash_sha256" in repr(execution)
    assert str(execution.id) in repr(execution)


def test_tool_execution_status_check_constraint(db_session: Session) -> None:
    """Verify check constraint on tool_executions status column."""
    org = Organization(name="CERT Epsilon")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Epsilon")
    db_session.add(case)
    db_session.commit()

    execution = ToolExecution(
        case_id=case.id,
        tool_name="hash_sha256",
        tool_version="1.0.0",
        agent_role="Executor",
        status="invalid_status",  # type: ignore
    )
    db_session.add(execution)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_tool_execution_duration_check_constraint(db_session: Session) -> None:
    """Verify check constraint that duration_ms must be non-negative."""
    org = Organization(name="CERT Zeta")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Zeta")
    db_session.add(case)
    db_session.commit()

    execution = ToolExecution(
        case_id=case.id,
        tool_name="hash_sha256",
        tool_version="1.0.0",
        agent_role="Executor",
        duration_ms=-1,
    )
    db_session.add(execution)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_observation_creation_and_defaults(db_session: Session) -> None:
    """Verify nominal creation of Observation, relations, and repr."""
    org = Organization(name="CERT Eta")
    user = User(email="analyst_eta@iryx.local", hashed_password="pw")
    db_session.add_all([org, user])
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Eta")
    db_session.add(case)
    db_session.commit()

    evidence = Evidence(
        case_id=case.id,
        original_name="syslog.log",
        file_size=1024,
        imported_by=user.id,
    )
    db_session.add(evidence)
    db_session.commit()

    execution = ToolExecution(
        case_id=case.id,
        tool_name="parse_text_logs",
        tool_version="1.0.0",
        agent_role="Executor",
    )
    db_session.add(execution)
    db_session.commit()

    now = datetime.now(UTC)
    obs = Observation(
        case_id=case.id,
        source_id=evidence.id,
        tool_name="parse_text_logs",
        tool_execution_id=execution.id,
        normalized_content={"event": "login_failed", "ip": "192.168.1.50"},
        timestamp_utc=now,
        source_location="line:142",
    )
    db_session.add(obs)
    db_session.commit()
    db_session.refresh(obs)

    assert isinstance(obs.id, uuid.UUID)
    assert obs.case_id == case.id
    assert obs.source_id == evidence.id
    assert obs.tool_execution_id == execution.id
    assert obs.tool_name == "parse_text_logs"
    assert obs.normalized_content["event"] == "login_failed"
    assert obs.source_location == "line:142"
    assert obs.created_at is not None
    assert obs.case.id == case.id
    assert obs.evidence.id == evidence.id  # type: ignore
    assert obs.tool_execution.id == execution.id  # type: ignore
    assert "parse_text_logs" in repr(obs)


def test_cascade_delete_from_case(db_session: Session) -> None:
    """Verify deleting a Case cascades to ToolExecution and Observation."""
    org = Organization(name="CERT Theta")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Theta")
    db_session.add(case)
    db_session.commit()

    execution = ToolExecution(
        case_id=case.id,
        tool_name="hash_sha256",
        tool_version="1.0.0",
        agent_role="Executor",
    )
    db_session.add(execution)
    db_session.commit()

    obs = Observation(
        case_id=case.id,
        tool_name="hash_sha256",
        tool_execution_id=execution.id,
        normalized_content={"hash": "abcdef"},
    )
    db_session.add(obs)
    db_session.commit()

    execution_id = execution.id
    obs_id = obs.id

    # Delete case
    db_session.delete(case)
    db_session.commit()

    assert db_session.get(ToolExecution, execution_id) is None
    assert db_session.get(Observation, obs_id) is None


def test_cascade_delete_from_evidence(db_session: Session) -> None:
    """Verify deleting an Evidence cascades to related Observation records."""
    org = Organization(name="CERT Iota")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Iota")
    db_session.add(case)
    db_session.commit()

    evidence = Evidence(
        case_id=case.id,
        original_name="test.evtx",
        file_size=2048,
    )
    db_session.add(evidence)
    db_session.commit()

    obs = Observation(
        case_id=case.id,
        source_id=evidence.id,
        tool_name="parse_evtx",
        normalized_content={"event_id": 4624},
    )
    db_session.add(obs)
    db_session.commit()

    obs_id = obs.id

    # Delete evidence
    db_session.delete(evidence)
    db_session.commit()

    assert db_session.get(Observation, obs_id) is None


def test_cascade_delete_from_tool_execution(db_session: Session) -> None:
    """Verify deleting a ToolExecution cascades to related Observation records."""
    org = Organization(name="CERT Kappa")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Kappa")
    db_session.add(case)
    db_session.commit()

    execution = ToolExecution(
        case_id=case.id,
        tool_name="parse_registry",
        tool_version="1.0.0",
        agent_role="Executor",
    )
    db_session.add(execution)
    db_session.commit()

    obs = Observation(
        case_id=case.id,
        tool_name="parse_registry",
        tool_execution_id=execution.id,
        normalized_content={"key": "RunOnce"},
    )
    db_session.add(obs)
    db_session.commit()

    obs_id = obs.id

    # Delete execution
    db_session.delete(execution)
    db_session.commit()

    assert db_session.get(Observation, obs_id) is None
