"""Integration tests for Evidence Upload API (POST /api/v1/cases/{case_id}/evidences)."""

import io
import tempfile
import uuid
from collections.abc import Generator
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

        # Verify Location header (Acceptance Criteria)
        expected_location = f"/api/v1/cases/{case.id}/evidences/{evidence_id}/ingestion-status"
        assert response.headers.get("Location") == expected_location

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
