"""Integration tests for Evidence Upload, Status Polling, Pagination, and Detail APIs."""

import io
import tempfile
import uuid
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.api.dependencies import get_db
from iryx.auth.models import MembershipRole, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.models import Case
from iryx.core.config import Settings
from iryx.core.security import create_access_token
from iryx.db.base import Base
from iryx.evidence.models import Evidence, IngestionRun, IngestionStatus
from iryx.main import app
from iryx.organizations.services import OrganizationService


@pytest.fixture
def temp_staging() -> Generator[Path, None, None]:
    """Temporary staging folder isolated for integration tests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def integration_settings(temp_staging: Path) -> Settings:
    """Settings overriding staging path to the isolated directory."""
    return Settings(
        secret_key="integration-test-secret-key-32-chars-minimum",
        evidence_storage_path=str(temp_staging.parent),
        evidence_staging_path=str(temp_staging),
        max_evidence_size_gb=1,
    )


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an in-memory SQLite database session isolated for integration testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()

    def override_get_db() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_db, None)
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Provide a TestClient bound to the isolated session."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def test_setup(db_session: Session) -> dict[str, object]:
    """Create test organizations, users, and cases with varying membership roles."""
    user_svc = UserService(db_session)
    org_svc = OrganizationService(db_session)

    analyst = user_svc.create_user(UserCreate(email="analyst@soc.iryx", password="Password123!"))
    investigator = user_svc.create_user(
        UserCreate(email="investigator@soc.iryx", password="Password123!")
    )
    outsider = user_svc.create_user(UserCreate(email="outsider@soc.iryx", password="Password123!"))

    # Organization 1: Case owner
    org = org_svc.create_organization(name="SOC IRYX Primary", creator_id=analyst.id)
    org_svc.add_member(org_id=org.id, user_id=investigator.id, role=MembershipRole.INVESTIGATOR)

    # Organization 2: Unrelated org for outsider
    other_org = org_svc.create_organization(name="SOC External", creator_id=outsider.id)

    # Case owned by Organization 1
    case = Case(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Dossier Forensique 001",
        status="open",
        description="Investigation sur suspicion de ransomware",
        created_by=analyst.id,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    return {
        "org": org,
        "other_org": other_org,
        "case": case,
        "analyst": analyst,
        "investigator": investigator,
        "outsider": outsider,
    }


def auth_header(user: User) -> dict[str, str]:
    """Generate Authorization header with Bearer JWT for specified user."""
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


def test_upload_evidence_nominal_success(
    client: TestClient,
    test_setup: dict[str, object],
    db_session: Session,
    integration_settings: Settings,
    temp_staging: Path,
) -> None:
    """Verify nominal upload returns HTTP 202, Location header, and persists entities."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    file_bytes = b"EVTX Binary Content Header and Events Payload"
    files = {"file": ("sysmon.evtx", io.BytesIO(file_bytes), "application/octet-stream")}

    with (
        patch("iryx.evidence.services.get_settings", return_value=integration_settings),
        patch("iryx.evidence.services.process_evidence_ingestion.delay") as mock_celery,
    ):
        response = client.post(
            f"/api/v1/cases/{case.id}/evidences",
            headers=auth_header(analyst),
            files=files,
        )

        assert response.status_code == 202
        data = response.json()
        assert "evidence_id" in data
        assert "ingestion_run_id" in data

        evidence_id = uuid.UUID(data["evidence_id"])
        ingestion_run_id = uuid.UUID(data["ingestion_run_id"])

        # Verify Location and Retry-After headers (ADR-0008)
        expected_location = f"/api/v1/cases/{case.id}/evidences/{evidence_id}/ingestion-status"
        assert response.headers.get("Location") == expected_location
        assert response.headers.get("Retry-After") == "3"

        # Verify DB Evidence entity
        evidence = db_session.get(Evidence, evidence_id)
        assert evidence is not None
        assert evidence.case_id == case.id
        assert evidence.original_name == "sysmon.evtx"
        assert evidence.file_size == len(file_bytes)
        assert evidence.imported_by == analyst.id

        # Verify DB IngestionRun entity
        ingestion_run = db_session.get(IngestionRun, ingestion_run_id)
        assert ingestion_run is not None
        assert ingestion_run.evidence_id == evidence_id
        assert ingestion_run.status == IngestionStatus.PENDING
        assert ingestion_run.progress == 0

        # Verify physical staging file exists on disk
        staging_file = temp_staging / f"{evidence_id}.bin"
        assert staging_file.exists()
        assert staging_file.read_bytes() == file_bytes

        # Verify background Celery task dispatch
        mock_celery.assert_called_once_with(str(evidence_id), str(staging_file))


def test_upload_evidence_homonym_protection(
    client: TestClient,
    test_setup: dict[str, object],
    db_session: Session,
    integration_settings: Settings,
    temp_staging: Path,
) -> None:
    """Verify re-uploading the same filename creates a new evidence without overwriting."""
    case: Case = test_setup["case"]  # type: ignore
    investigator: User = test_setup["investigator"]  # type: ignore

    file1 = b"First capture version"
    file2 = b"Second capture version - identical filename"

    with (
        patch("iryx.evidence.services.get_settings", return_value=integration_settings),
        patch("iryx.evidence.services.process_evidence_ingestion.delay"),
    ):
        # First upload
        res1 = client.post(
            f"/api/v1/cases/{case.id}/evidences",
            headers=auth_header(investigator),
            files={"file": ("memory.dmp", io.BytesIO(file1), "application/octet-stream")},
        )
        assert res1.status_code == 202
        ev1_id = uuid.UUID(res1.json()["evidence_id"])

        # Second upload with identical original filename
        res2 = client.post(
            f"/api/v1/cases/{case.id}/evidences",
            headers=auth_header(investigator),
            files={"file": ("memory.dmp", io.BytesIO(file2), "application/octet-stream")},
        )
        assert res2.status_code == 202
        ev2_id = uuid.UUID(res2.json()["evidence_id"])

        # Different entities created
        assert ev1_id != ev2_id

        # Verify both staging files co-exist
        path1 = temp_staging / f"{ev1_id}.bin"
        path2 = temp_staging / f"{ev2_id}.bin"
        assert path1.exists()
        assert path2.exists()
        assert path1.read_bytes() == file1
        assert path2.read_bytes() == file2

        # Verify both records in DB
        records = db_session.query(Evidence).filter(Evidence.case_id == case.id).all()
        assert len(records) == 2
        assert records[0].original_name == "memory.dmp"
        assert records[1].original_name == "memory.dmp"


def test_upload_evidence_empty_file_rejected(
    client: TestClient,
    test_setup: dict[str, object],
    integration_settings: Settings,
    temp_staging: Path,
) -> None:
    """Verify empty file (0 bytes) returns HTTP 400 Bad Request with EMPTY_FILE_ERROR."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    with patch("iryx.evidence.services.get_settings", return_value=integration_settings):
        response = client.post(
            f"/api/v1/cases/{case.id}/evidences",
            headers=auth_header(analyst),
            files={"file": ("empty.raw", io.BytesIO(b""), "application/octet-stream")},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "EMPTY_FILE_ERROR"
        assert "vide" in data["error"]["message"].lower()

        # Verify no orphan file left on disk
        assert len(list(temp_staging.glob("*.bin"))) == 0


def test_upload_evidence_missing_file_rejected(
    client: TestClient,
    test_setup: dict[str, object],
) -> None:
    """Verify request without 'file' field returns HTTP 422 Unprocessable Content."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    # Send multipart form data without the file field
    response = client.post(
        f"/api/v1/cases/{case.id}/evidences",
        headers=auth_header(analyst),
        data={"some_field": "some_value"},
    )

    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


def test_upload_evidence_case_not_found(
    client: TestClient,
    test_setup: dict[str, object],
    integration_settings: Settings,
    temp_staging: Path,
) -> None:
    """Verify upload to non-existent case_id returns HTTP 404 without writing to disk."""
    analyst: User = test_setup["analyst"]  # type: ignore
    fake_case_id = uuid.uuid4()

    with patch("iryx.evidence.services.get_settings", return_value=integration_settings):
        response = client.post(
            f"/api/v1/cases/{fake_case_id}/evidences",
            headers=auth_header(analyst),
            files={"file": ("log.txt", io.BytesIO(b"Some text log content"), "text/plain")},
        )

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "CASE_NOT_FOUND"

        # Verify no staging file created
        assert len(list(temp_staging.glob("*.bin"))) == 0


def test_upload_evidence_unauthorized_outsider(
    client: TestClient,
    test_setup: dict[str, object],
    integration_settings: Settings,
    temp_staging: Path,
) -> None:
    """Verify user not belonging to case's organization returns HTTP 403 Forbidden."""
    case: Case = test_setup["case"]  # type: ignore
    outsider: User = test_setup["outsider"]  # type: ignore

    with patch("iryx.evidence.services.get_settings", return_value=integration_settings):
        response = client.post(
            f"/api/v1/cases/{case.id}/evidences",
            headers=auth_header(outsider),
            files={
                "file": (
                    "intrusion.pcap",
                    io.BytesIO(b"Packet capture data"),
                    "application/vnd.tcpdump.pcap",
                )
            },
        )

        assert response.status_code == 403
        data = response.json()
        assert data["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

        # Verify no staging file created
        assert len(list(temp_staging.glob("*.bin"))) == 0


def test_upload_evidence_unauthenticated(
    client: TestClient,
    test_setup: dict[str, object],
    integration_settings: Settings,
    temp_staging: Path,
) -> None:
    """Verify request without Authorization header returns HTTP 401 Unauthorized."""
    case: Case = test_setup["case"]  # type: ignore

    with patch("iryx.evidence.services.get_settings", return_value=integration_settings):
        response = client.post(
            f"/api/v1/cases/{case.id}/evidences",
            files={"file": ("data.bin", io.BytesIO(b"Data"), "application/octet-stream")},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "UNAUTHORIZED"

        # Verify no staging file created
        assert len(list(temp_staging.glob("*.bin"))) == 0


def test_upload_evidence_payload_too_large(
    client: TestClient,
    test_setup: dict[str, object],
    temp_staging: Path,
) -> None:
    """Verify upload exceeding max size returns HTTP 413 and purges staging file."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    oversized_settings = Settings(
        secret_key="integration-test-secret-key-32-chars-minimum",
        evidence_storage_path=str(temp_staging.parent),
        evidence_staging_path=str(temp_staging),
        max_evidence_size_gb=1,
    )

    with (
        patch("iryx.evidence.services.get_settings", return_value=oversized_settings),
        patch.object(oversized_settings, "max_evidence_size_gb", 0),  # Limit 0 bytes
    ):
        response = client.post(
            f"/api/v1/cases/{case.id}/evidences",
            headers=auth_header(analyst),
            files={"file": ("big_image.dd", io.BytesIO(b"X" * 1024), "application/octet-stream")},
        )

        assert response.status_code == 413
        data = response.json()
        assert data["error"]["code"] == "PAYLOAD_TOO_LARGE"

        # Verify staging file was purged
        assert len(list(temp_staging.glob("*.bin"))) == 0


# ============================================================================
# Story 3.4 : Polling Ingestion Status Tests
# ============================================================================


def test_get_ingestion_status_completed(
    client: TestClient,
    test_setup: dict[str, object],
    db_session: Session,
) -> None:
    """Verify polling completed ingestion returns HTTP 200 with sealed sha256 and detected_type."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case.id,
        original_name="target_binary.exe",
        file_size=2048,
        sha256="1" * 64,
        detected_type="application/x-executable",
        imported_by=analyst.id,
    )
    ingestion_run = IngestionRun(
        id=uuid.uuid4(),
        evidence_id=evidence.id,
        status=IngestionStatus.COMPLETED,
        progress=100,
        error_message=None,
    )
    db_session.add_all([evidence, ingestion_run])
    db_session.commit()

    response = client.get(
        f"/api/v1/cases/{case.id}/evidences/{evidence.id}/ingestion-status",
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["progress"] == 100
    assert data["error_message"] is None
    assert data["sha256"] == "1" * 64
    assert data["detected_type"] == "application/x-executable"
    # No Retry-After header on completed task
    assert "Retry-After" not in response.headers


def test_get_ingestion_status_processing(
    client: TestClient,
    test_setup: dict[str, object],
    db_session: Session,
) -> None:
    """Verify polling processing ingestion returns HTTP 200 with Retry-After: 3."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case.id,
        original_name="memory.raw",
        file_size=4096,
        sha256=None,
        detected_type=None,
        imported_by=analyst.id,
    )
    ingestion_run = IngestionRun(
        id=uuid.uuid4(),
        evidence_id=evidence.id,
        status=IngestionStatus.PROCESSING,
        progress=20,
        error_message=None,
    )
    db_session.add_all([evidence, ingestion_run])
    db_session.commit()

    response = client.get(
        f"/api/v1/cases/{case.id}/evidences/{evidence.id}/ingestion-status",
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processing"
    assert data["progress"] == 20
    assert data["error_message"] is None
    assert data["sha256"] is None
    assert data["detected_type"] is None
    # ADR-0008: Retry-After: 3 on in-progress polling
    assert response.headers.get("Retry-After") == "3"


def test_get_ingestion_status_pending(
    client: TestClient,
    test_setup: dict[str, object],
    db_session: Session,
) -> None:
    """Verify polling pending ingestion returns HTTP 200 with Retry-After: 3."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case.id,
        original_name="queued.raw",
        file_size=1024,
        sha256=None,
        detected_type=None,
        imported_by=analyst.id,
    )
    ingestion_run = IngestionRun(
        id=uuid.uuid4(),
        evidence_id=evidence.id,
        status=IngestionStatus.PENDING,
        progress=0,
        error_message=None,
    )
    db_session.add_all([evidence, ingestion_run])
    db_session.commit()

    response = client.get(
        f"/api/v1/cases/{case.id}/evidences/{evidence.id}/ingestion-status",
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["progress"] == 0
    assert data["error_message"] is None
    assert data["sha256"] is None
    assert data["detected_type"] is None
    assert response.headers.get("Retry-After") == "3"


def test_get_ingestion_status_failed(
    client: TestClient,
    test_setup: dict[str, object],
    db_session: Session,
) -> None:
    """Verify polling failed ingestion returns HTTP 200 with error_message."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case.id,
        original_name="broken.bin",
        file_size=1024,
        sha256=None,
        detected_type=None,
        imported_by=analyst.id,
    )
    ingestion_run = IngestionRun(
        id=uuid.uuid4(),
        evidence_id=evidence.id,
        status=IngestionStatus.FAILED,
        progress=40,
        error_message="Hash computation IO failure",
    )
    db_session.add_all([evidence, ingestion_run])
    db_session.commit()

    response = client.get(
        f"/api/v1/cases/{case.id}/evidences/{evidence.id}/ingestion-status",
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["progress"] == 40
    assert data["error_message"] == "Hash computation IO failure"
    assert data["sha256"] is None
    assert data["detected_type"] is None


def test_get_ingestion_status_evidence_not_found(
    client: TestClient,
    test_setup: dict[str, object],
) -> None:
    """Verify unknown evidence_id returns HTTP 404 with EVIDENCE_NOT_FOUND_IN_CASE."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore
    unknown_evidence_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/cases/{case.id}/evidences/{unknown_evidence_id}/ingestion-status",
        headers=auth_header(analyst),
    )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "EVIDENCE_NOT_FOUND_IN_CASE"


def test_get_ingestion_status_evidence_in_other_case(
    client: TestClient,
    test_setup: dict[str, object],
    db_session: Session,
) -> None:
    """Verify requesting evidence from other case returns 404 EVIDENCE_NOT_FOUND_IN_CASE."""
    case: Case = test_setup["case"]  # type: ignore
    org = test_setup["org"]
    analyst: User = test_setup["analyst"]  # type: ignore

    # Create another case in the same organization
    other_case = Case(
        id=uuid.uuid4(),
        organization_id=org.id,  # type: ignore
        title="Dossier Autre",
        status="open",
        created_by=analyst.id,
    )
    evidence_in_other = Evidence(
        id=uuid.uuid4(),
        case_id=other_case.id,
        original_name="other_case_evidence.raw",
        file_size=512,
        imported_by=analyst.id,
    )
    db_session.add_all([other_case, evidence_in_other])
    db_session.commit()

    # Query with case.id but other_case's evidence.id
    response = client.get(
        f"/api/v1/cases/{case.id}/evidences/{evidence_in_other.id}/ingestion-status",
        headers=auth_header(analyst),
    )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "EVIDENCE_NOT_FOUND_IN_CASE"


# ============================================================================
# Story 3.4 : Evidence Detail Metadata Tests
# ============================================================================


def test_get_evidence_detail_nominal(
    client: TestClient,
    test_setup: dict[str, object],
    db_session: Session,
) -> None:
    """Verify GET /evidences/{evidence_id} returns complete EvidenceRead schema."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=case.id,
        original_name="disk_image.e01",
        file_size=1048576,
        sha256="e" * 64,
        detected_type="application/octet-stream",
        imported_by=analyst.id,
    )
    db_session.add(evidence)
    db_session.commit()

    response = client.get(
        f"/api/v1/cases/{case.id}/evidences/{evidence.id}",
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(evidence.id)
    assert data["case_id"] == str(case.id)
    assert data["original_name"] == "disk_image.e01"
    assert data["file_size"] == 1048576
    assert data["sha256"] == "e" * 64
    assert data["detected_type"] == "application/octet-stream"
    assert data["imported_by"] == str(analyst.id)
    assert "created_at" in data


def test_get_evidence_detail_not_found(
    client: TestClient,
    test_setup: dict[str, object],
) -> None:
    """Verify detail for non-existent evidence returns HTTP 404 EVIDENCE_NOT_FOUND_IN_CASE."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    response = client.get(
        f"/api/v1/cases/{case.id}/evidences/{uuid.uuid4()}",
        headers=auth_header(analyst),
    )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "EVIDENCE_NOT_FOUND_IN_CASE"


def test_get_evidence_detail_cross_case_not_found(
    client: TestClient,
    test_setup: dict[str, object],
    db_session: Session,
) -> None:
    """Verify evidence from another case returns HTTP 404 EVIDENCE_NOT_FOUND_IN_CASE."""
    case: Case = test_setup["case"]  # type: ignore
    org = test_setup["org"]
    analyst: User = test_setup["analyst"]  # type: ignore

    other_case = Case(
        id=uuid.uuid4(),
        organization_id=org.id,  # type: ignore
        title="Dossier Autre 2",
        status="open",
        created_by=analyst.id,
    )
    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=other_case.id,
        original_name="secret.bin",
        file_size=256,
        imported_by=analyst.id,
    )
    db_session.add_all([other_case, evidence])
    db_session.commit()

    response = client.get(
        f"/api/v1/cases/{case.id}/evidences/{evidence.id}",
        headers=auth_header(analyst),
    )

    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "EVIDENCE_NOT_FOUND_IN_CASE"


# ============================================================================
# Story 3.4 : Paged Collection of Evidences Tests
# ============================================================================


def test_list_evidences_nominal_pagination(
    client: TestClient,
    test_setup: dict[str, object],
    db_session: Session,
) -> None:
    """Verify GET /evidences returns paginated items with total, limit, offset, and has_more."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    now = datetime.now(UTC)
    for i in range(3):
        ev = Evidence(
            id=uuid.uuid4(),
            case_id=case.id,
            original_name=f"artifact_{i}.bin",
            file_size=100 * (i + 1),
            imported_by=analyst.id,
            created_at=now + timedelta(seconds=i),
        )
        db_session.add(ev)
    db_session.commit()

    # Page 1: limit 2, offset 0
    res1 = client.get(
        f"/api/v1/cases/{case.id}/evidences?limit=2&offset=0",
        headers=auth_header(analyst),
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert len(data1["items"]) == 2
    assert data1["total"] == 3
    assert data1["total_items"] == 3
    assert data1["limit"] == 2
    assert data1["offset"] == 0
    assert data1["has_more"] is True
    # Verify deterministic sorting (created_at DESC): artifact_2 then artifact_1
    assert data1["items"][0]["original_name"] == "artifact_2.bin"
    assert data1["items"][1]["original_name"] == "artifact_1.bin"

    # Page 2: limit 2, offset 2
    res2 = client.get(
        f"/api/v1/cases/{case.id}/evidences?limit=2&offset=2",
        headers=auth_header(analyst),
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert len(data2["items"]) == 1
    assert data2["total"] == 3
    assert data2["total_items"] == 3
    assert data2["limit"] == 2
    assert data2["offset"] == 2
    assert data2["has_more"] is False
    assert data2["items"][0]["original_name"] == "artifact_0.bin"


def test_list_evidences_default_pagination(
    client: TestClient,
    test_setup: dict[str, object],
    db_session: Session,
) -> None:
    """Verify default pagination parameters are limit=50 and offset=0."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    response = client.get(
        f"/api/v1/cases/{case.id}/evidences",
        headers=auth_header(analyst),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert data["has_more"] is False


@pytest.mark.parametrize("invalid_query", ["limit=150", "limit=0", "offset=-1"])
def test_list_evidences_pagination_limits_validation(
    client: TestClient,
    test_setup: dict[str, object],
    invalid_query: str,
) -> None:
    """Verify limit > 100, limit < 1, or offset < 0 returns HTTP 422 Unprocessable Content."""
    case: Case = test_setup["case"]  # type: ignore
    analyst: User = test_setup["analyst"]  # type: ignore

    response = client.get(
        f"/api/v1/cases/{case.id}/evidences?{invalid_query}",
        headers=auth_header(analyst),
    )

    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


# ============================================================================
# Story 3.4 : Security, RBAC, and Authentication Tests
# ============================================================================


def test_evidence_endpoints_unauthenticated(
    client: TestClient,
    test_setup: dict[str, object],
) -> None:
    """Verify unauthenticated requests return HTTP 401 UNAUTHORIZED on all GET routes."""
    case: Case = test_setup["case"]  # type: ignore
    fake_id = uuid.uuid4()

    # Status endpoint
    r1 = client.get(f"/api/v1/cases/{case.id}/evidences/{fake_id}/ingestion-status")
    assert r1.status_code == 401
    assert r1.json()["error"]["code"] == "UNAUTHORIZED"

    # List endpoint
    r2 = client.get(f"/api/v1/cases/{case.id}/evidences")
    assert r2.status_code == 401
    assert r2.json()["error"]["code"] == "UNAUTHORIZED"

    # Detail endpoint
    r3 = client.get(f"/api/v1/cases/{case.id}/evidences/{fake_id}")
    assert r3.status_code == 401
    assert r3.json()["error"]["code"] == "UNAUTHORIZED"


def test_evidence_endpoints_outsider_forbidden(
    client: TestClient,
    test_setup: dict[str, object],
) -> None:
    """Verify outsider from another organization returns HTTP 403 INSUFFICIENT_PERMISSIONS."""
    case: Case = test_setup["case"]  # type: ignore
    outsider: User = test_setup["outsider"]  # type: ignore
    fake_id = uuid.uuid4()

    # Status endpoint
    r1 = client.get(
        f"/api/v1/cases/{case.id}/evidences/{fake_id}/ingestion-status",
        headers=auth_header(outsider),
    )
    assert r1.status_code == 403
    assert r1.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

    # List endpoint
    r2 = client.get(
        f"/api/v1/cases/{case.id}/evidences",
        headers=auth_header(outsider),
    )
    assert r2.status_code == 403
    assert r2.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"

    # Detail endpoint
    r3 = client.get(
        f"/api/v1/cases/{case.id}/evidences/{fake_id}",
        headers=auth_header(outsider),
    )
    assert r3.status_code == 403
    assert r3.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_evidence_endpoints_case_not_found(
    client: TestClient,
    test_setup: dict[str, object],
) -> None:
    """Verify non-existent case_id returns HTTP 404 CASE_NOT_FOUND on all endpoints."""
    analyst: User = test_setup["analyst"]  # type: ignore
    fake_case_id = uuid.uuid4()
    fake_evidence_id = uuid.uuid4()

    # Polling status
    r1 = client.get(
        f"/api/v1/cases/{fake_case_id}/evidences/{fake_evidence_id}/ingestion-status",
        headers=auth_header(analyst),
    )
    assert r1.status_code == 404
    assert r1.json()["error"]["code"] == "CASE_NOT_FOUND"

    # Paged list
    r2 = client.get(
        f"/api/v1/cases/{fake_case_id}/evidences",
        headers=auth_header(analyst),
    )
    assert r2.status_code == 404
    assert r2.json()["error"]["code"] == "CASE_NOT_FOUND"

    # Detail
    r3 = client.get(
        f"/api/v1/cases/{fake_case_id}/evidences/{fake_evidence_id}",
        headers=auth_header(analyst),
    )
    assert r3.status_code == 404
    assert r3.json()["error"]["code"] == "CASE_NOT_FOUND"
