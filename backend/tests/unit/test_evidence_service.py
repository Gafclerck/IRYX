"""Unit tests for EvidenceService: get_evidence, get_ingestion_status, and list_evidences."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.auth.models import Organization, User
from iryx.cases.models import Case
from iryx.core.exceptions import (
    EvidenceNotFoundInCaseException,
    ValidationException,
)
from iryx.db.base import Base
from iryx.evidence.models import Evidence, IngestionRun, IngestionStatus
from iryx.evidence.services import EvidenceService


@pytest.fixture
def db_session() -> Session:
    """In-memory SQLite database session isolated for unit testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_data(db_session: Session) -> dict[str, object]:
    """Seed test user, organization, cases, and evidences."""
    user = User(
        id=uuid.uuid4(),
        email="analyst@soc.iryx",
        hashed_password="hashed_pw_test",
        is_active=True,
    )
    org = Organization(id=uuid.uuid4(), name="SOC IRYX Test")
    case_a = Case(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Dossier A",
        status="open",
        created_by=user.id,
    )
    case_b = Case(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Dossier B",
        status="open",
        created_by=user.id,
    )
    db_session.add_all([user, org, case_a, case_b])
    db_session.commit()

    return {
        "user": user,
        "org": org,
        "case_a": case_a,
        "case_b": case_b,
    }


# ============================================================================
# get_evidence Tests
# ============================================================================


def test_get_evidence_nominal(db_session: Session, test_data: dict[str, object]) -> None:
    """Verify get_evidence retrieves evidence when it belongs to the case."""
    case_a: Case = test_data["case_a"]  # type: ignore
    user: User = test_data["user"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case_a.id,
        original_name="memory.dmp",
        file_size=1024,
        sha256="a" * 64,
        detected_type="application/octet-stream",
        imported_by=user.id,
    )
    db_session.add(evidence)
    db_session.commit()

    service = EvidenceService(db_session)
    retrieved = service.get_evidence(case_id=case_a.id, evidence_id=evidence.id)

    assert retrieved.id == evidence.id
    assert retrieved.original_name == "memory.dmp"
    assert retrieved.case_id == case_a.id


def test_get_evidence_nonexistent_raises_404(
    db_session: Session, test_data: dict[str, object]
) -> None:
    """Verify get_evidence raises EvidenceNotFoundInCaseException for unknown evidence_id."""
    case_a: Case = test_data["case_a"]  # type: ignore
    service = EvidenceService(db_session)

    with pytest.raises(EvidenceNotFoundInCaseException) as exc_info:
        service.get_evidence(case_id=case_a.id, evidence_id=uuid.uuid4())

    assert exc_info.value.code == "EVIDENCE_NOT_FOUND_IN_CASE"
    assert exc_info.value.status_code == 404


def test_get_evidence_other_case_raises_404(
    db_session: Session, test_data: dict[str, object]
) -> None:
    """Verify get_evidence raises EvidenceNotFoundInCaseException for cross-case access."""
    case_a: Case = test_data["case_a"]  # type: ignore
    case_b: Case = test_data["case_b"]  # type: ignore
    user: User = test_data["user"]  # type: ignore

    # Evidence belongs to case_b
    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case_b.id,
        original_name="disk.raw",
        file_size=2048,
        imported_by=user.id,
    )
    db_session.add(evidence)
    db_session.commit()

    service = EvidenceService(db_session)
    # Attempt to retrieve evidence with case_a
    with pytest.raises(EvidenceNotFoundInCaseException) as exc_info:
        service.get_evidence(case_id=case_a.id, evidence_id=evidence.id)

    assert exc_info.value.code == "EVIDENCE_NOT_FOUND_IN_CASE"
    assert exc_info.value.status_code == 404


# ============================================================================
# get_ingestion_status Tests
# ============================================================================


def test_get_ingestion_status_completed(
    db_session: Session, test_data: dict[str, object]
) -> None:
    """Verify get_ingestion_status returns completed run with sealed sha256 and detected_type."""
    case_a: Case = test_data["case_a"]  # type: ignore
    user: User = test_data["user"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case_a.id,
        original_name="sysmon.evtx",
        file_size=4096,
        sha256="c" * 64,
        detected_type="application/x-ms-evtx",
        imported_by=user.id,
    )
    ingestion_run = IngestionRun(
        id=uuid.uuid4(),
        evidence_id=evidence.id,
        status=IngestionStatus.COMPLETED,
        progress=100,
        error_message=None,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db_session.add_all([evidence, ingestion_run])
    db_session.commit()

    service = EvidenceService(db_session)
    status_resp = service.get_ingestion_status(case_id=case_a.id, evidence_id=evidence.id)

    assert status_resp.status == IngestionStatus.COMPLETED
    assert status_resp.progress == 100
    assert status_resp.error_message is None
    assert status_resp.sha256 == "c" * 64
    assert status_resp.detected_type == "application/x-ms-evtx"


def test_get_ingestion_status_processing(
    db_session: Session, test_data: dict[str, object]
) -> None:
    """Verify get_ingestion_status returns processing run with progress and null metadata."""
    case_a: Case = test_data["case_a"]  # type: ignore
    user: User = test_data["user"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case_a.id,
        original_name="network.pcap",
        file_size=8192,
        sha256=None,
        detected_type=None,
        imported_by=user.id,
    )
    ingestion_run = IngestionRun(
        id=uuid.uuid4(),
        evidence_id=evidence.id,
        status=IngestionStatus.PROCESSING,
        progress=20,
        error_message=None,
        started_at=datetime.now(UTC),
    )
    db_session.add_all([evidence, ingestion_run])
    db_session.commit()

    service = EvidenceService(db_session)
    status_resp = service.get_ingestion_status(case_id=case_a.id, evidence_id=evidence.id)

    assert status_resp.status == IngestionStatus.PROCESSING
    assert status_resp.progress == 20
    assert status_resp.error_message is None
    assert status_resp.sha256 is None
    assert status_resp.detected_type is None


def test_get_ingestion_status_failed(
    db_session: Session, test_data: dict[str, object]
) -> None:
    """Verify get_ingestion_status returns failed run with error message."""
    case_a: Case = test_data["case_a"]  # type: ignore
    user: User = test_data["user"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case_a.id,
        original_name="corrupt.raw",
        file_size=512,
        sha256=None,
        detected_type=None,
        imported_by=user.id,
    )
    ingestion_run = IngestionRun(
        id=uuid.uuid4(),
        evidence_id=evidence.id,
        status=IngestionStatus.FAILED,
        progress=35,
        error_message="CRC verification failure",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    db_session.add_all([evidence, ingestion_run])
    db_session.commit()

    service = EvidenceService(db_session)
    status_resp = service.get_ingestion_status(case_id=case_a.id, evidence_id=evidence.id)

    assert status_resp.status == IngestionStatus.FAILED
    assert status_resp.progress == 35
    assert status_resp.error_message == "CRC verification failure"
    assert status_resp.sha256 is None
    assert status_resp.detected_type is None


def test_get_ingestion_status_picks_latest_run(
    db_session: Session, test_data: dict[str, object]
) -> None:
    """Verify get_ingestion_status queries the latest IngestionRun by started_at."""
    case_a: Case = test_data["case_a"]  # type: ignore
    user: User = test_data["user"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case_a.id,
        original_name="multi_run.bin",
        file_size=1024,
        sha256="d" * 64,
        detected_type="application/octet-stream",
        imported_by=user.id,
    )
    now = datetime.now(UTC)
    run_old = IngestionRun(
        id=uuid.uuid4(),
        evidence_id=evidence.id,
        status=IngestionStatus.FAILED,
        progress=10,
        error_message="Worker timeout",
        started_at=now - timedelta(minutes=10),
        completed_at=now - timedelta(minutes=9),
    )
    run_new = IngestionRun(
        id=uuid.uuid4(),
        evidence_id=evidence.id,
        status=IngestionStatus.COMPLETED,
        progress=100,
        error_message=None,
        started_at=now,
        completed_at=now,
    )
    db_session.add_all([evidence, run_old, run_new])
    db_session.commit()

    service = EvidenceService(db_session)
    status_resp = service.get_ingestion_status(case_id=case_a.id, evidence_id=evidence.id)

    assert status_resp.status == IngestionStatus.COMPLETED
    assert status_resp.progress == 100
    assert status_resp.error_message is None


def test_get_ingestion_status_no_run_fallback(
    db_session: Session, test_data: dict[str, object]
) -> None:
    """Verify fallback response if evidence has no ingestion run records."""
    case_a: Case = test_data["case_a"]  # type: ignore
    user: User = test_data["user"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case_a.id,
        original_name="orphan_run.bin",
        file_size=100,
        imported_by=user.id,
    )
    db_session.add(evidence)
    db_session.commit()

    service = EvidenceService(db_session)
    status_resp = service.get_ingestion_status(case_id=case_a.id, evidence_id=evidence.id)

    assert status_resp.status == IngestionStatus.PENDING
    assert status_resp.progress == 0
    assert status_resp.error_message is None


def test_get_ingestion_status_cross_case_raises_404(
    db_session: Session, test_data: dict[str, object]
) -> None:
    """Verify get_ingestion_status raises EvidenceNotFoundInCaseException for cross-case."""
    case_a: Case = test_data["case_a"]  # type: ignore
    case_b: Case = test_data["case_b"]  # type: ignore
    user: User = test_data["user"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case_b.id,
        original_name="evidence_b.bin",
        file_size=200,
        imported_by=user.id,
    )
    db_session.add(evidence)
    db_session.commit()

    service = EvidenceService(db_session)
    with pytest.raises(EvidenceNotFoundInCaseException):
        service.get_ingestion_status(case_id=case_a.id, evidence_id=evidence.id)


# ============================================================================
# list_evidences Tests
# ============================================================================


def test_list_evidences_nominal(db_session: Session, test_data: dict[str, object]) -> None:
    """Verify list_evidences returns items and correct total count."""
    case_a: Case = test_data["case_a"]  # type: ignore
    user: User = test_data["user"]  # type: ignore

    now = datetime.now(UTC)
    evidences = [
        Evidence(
            id=uuid.uuid4(),
            case_id=case_a.id,
            original_name=f"evidence_{i}.raw",
            file_size=1000 + i,
            imported_by=user.id,
            created_at=now + timedelta(seconds=i),
        )
        for i in range(5)
    ]
    db_session.add_all(evidences)
    db_session.commit()

    service = EvidenceService(db_session)
    items, total = service.list_evidences(case_id=case_a.id, limit=3, offset=0)

    assert total == 5
    assert len(items) == 3
    # Deterministic order: created_at DESC, id DESC
    assert items[0].original_name == "evidence_4.raw"
    assert items[1].original_name == "evidence_3.raw"
    assert items[2].original_name == "evidence_2.raw"


def test_list_evidences_offset(db_session: Session, test_data: dict[str, object]) -> None:
    """Verify offset correctly slices the result list."""
    case_a: Case = test_data["case_a"]  # type: ignore
    user: User = test_data["user"]  # type: ignore

    now = datetime.now(UTC)
    evidences = [
        Evidence(
            id=uuid.uuid4(),
            case_id=case_a.id,
            original_name=f"evidence_{i}.raw",
            file_size=1000 + i,
            imported_by=user.id,
            created_at=now + timedelta(seconds=i),
        )
        for i in range(5)
    ]
    db_session.add_all(evidences)
    db_session.commit()

    service = EvidenceService(db_session)
    items, total = service.list_evidences(case_id=case_a.id, limit=2, offset=3)

    assert total == 5
    assert len(items) == 2
    assert items[0].original_name == "evidence_1.raw"
    assert items[1].original_name == "evidence_0.raw"


def test_list_evidences_empty_case(db_session: Session, test_data: dict[str, object]) -> None:
    """Verify list_evidences returns empty list and total 0 for empty case."""
    case_a: Case = test_data["case_a"]  # type: ignore
    service = EvidenceService(db_session)
    items, total = service.list_evidences(case_id=case_a.id, limit=50, offset=0)

    assert total == 0
    assert items == []


def test_list_evidences_does_not_leak_other_cases(
    db_session: Session, test_data: dict[str, object]
) -> None:
    """Verify list_evidences strictly filters by case_id."""
    case_a: Case = test_data["case_a"]  # type: ignore
    case_b: Case = test_data["case_b"]  # type: ignore
    user: User = test_data["user"]  # type: ignore

    ev_a = Evidence(
        id=uuid.uuid4(),
        case_id=case_a.id,
        original_name="evidence_a.bin",
        file_size=100,
        imported_by=user.id,
    )
    ev_b = Evidence(
        id=uuid.uuid4(),
        case_id=case_b.id,
        original_name="evidence_b.bin",
        file_size=200,
        imported_by=user.id,
    )
    db_session.add_all([ev_a, ev_b])
    db_session.commit()

    service = EvidenceService(db_session)
    items, total = service.list_evidences(case_id=case_a.id, limit=50, offset=0)

    assert total == 1
    assert len(items) == 1
    assert items[0].id == ev_a.id


@pytest.mark.parametrize("invalid_limit", [0, -1, 101, 200])
def test_list_evidences_invalid_limit_raises_validation_error(
    db_session: Session, test_data: dict[str, object], invalid_limit: int
) -> None:
    """Verify list_evidences rejects limit < 1 or limit > 100 with ValidationException."""
    case_a: Case = test_data["case_a"]  # type: ignore
    service = EvidenceService(db_session)

    with pytest.raises(ValidationException):
        service.list_evidences(case_id=case_a.id, limit=invalid_limit, offset=0)


def test_list_evidences_negative_offset_raises_validation_error(
    db_session: Session, test_data: dict[str, object]
) -> None:
    """Verify list_evidences rejects offset < 0 with ValidationException."""
    case_a: Case = test_data["case_a"]  # type: ignore
    service = EvidenceService(db_session)

    with pytest.raises(ValidationException):
        service.list_evidences(case_id=case_a.id, limit=50, offset=-1)


def test_list_evidences_offset_beyond_total_short_circuits(
    db_session: Session, test_data: dict[str, object]
) -> None:
    """Verify list_evidences short-circuits and returns empty list when offset >= total."""
    case_a: Case = test_data["case_a"]  # type: ignore
    service = EvidenceService(db_session)
    items, total = service.list_evidences(case_id=case_a.id, limit=50, offset=10)
    assert total == 0
    assert items == []


def test_get_ingestion_status_masks_sha256_until_completed(
    db_session: Session, test_data: dict[str, object]
) -> None:
    """Verify get_ingestion_status hides sha256 and detected_type before completed."""
    case_a: Case = test_data["case_a"]  # type: ignore
    user: User = test_data["user"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case_a.id,
        original_name="test.raw",
        file_size=1024,
        sha256="pre_calculated_sha",
        detected_type="text/plain",
        imported_by=user.id,
    )
    ingestion_run = IngestionRun(
        id=uuid.uuid4(),
        evidence_id=evidence.id,
        status=IngestionStatus.PROCESSING,
        progress=50,
        started_at=datetime.now(UTC),
    )
    db_session.add_all([evidence, ingestion_run])
    db_session.commit()

    service = EvidenceService(db_session)
    status_resp = service.get_ingestion_status(case_id=case_a.id, evidence_id=evidence.id)

    assert status_resp.status == IngestionStatus.PROCESSING
    assert status_resp.sha256 is None
    assert status_resp.detected_type is None


def test_evidence_list_response_populate_total_items_when_none() -> None:
    """Verify populate_total_items populates total_items if passed as None in dict."""
    from iryx.evidence.schemas import EvidenceListResponse

    resp = EvidenceListResponse(
        items=[],
        total=42,
        total_items=None,  # type: ignore
        limit=50,
        offset=0,
        has_more=False,
    )
    assert resp.total_items == 42
