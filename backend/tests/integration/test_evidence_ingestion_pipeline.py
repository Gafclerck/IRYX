"""Integration tests for the complete Evidence Ingestion Pipeline (Story 3.3)."""

import contextlib
import hashlib
import io
import os
import stat
import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers

from iryx.auth.models import User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.models import Case
from iryx.core.config import Settings
from iryx.db.base import Base
from iryx.evidence.models import Evidence, IngestionRun, IngestionStatus
from iryx.evidence.services import EvidenceService
from iryx.evidence.tasks import process_evidence_ingestion
from iryx.organizations.services import OrganizationService

# Minimal valid PNG image payload
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
    b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Minimal valid ZIP archive header payload
ZIP_BYTES = (
    b"PK\x03\x04\x14\x00\x00\x00\x08\x00\x00\x00!\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00test"
    b"PK\x01\x02\x14\x00\x14\x00\x00\x00\x08\x00\x00\x00!\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00testPK\x05\x06\x00\x00\x00\x00"
    b"\x01\x00\x01\x002\x00\x00\x002\x00\x00\x00\x00\x00"
)


@pytest.fixture
def temp_staging() -> Generator[Path, None, None]:
    """Provide an isolated staging directory with cleanup handling read-only permissions."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        staging_path = Path(tmp_dir)
        yield staging_path
        # Reset file permissions before teardown
        for f in staging_path.glob("*"):
            with contextlib.suppress(Exception):
                os.chmod(f, stat.S_IWRITE | stat.S_IREAD)


@pytest.fixture
def pipeline_settings(temp_staging: Path) -> Settings:
    """Settings pointing staging path to isolated temporary location."""
    return Settings(
        secret_key="integration-pipeline-secret-key-32-chars-min",
        evidence_storage_path=str(temp_staging.parent),
        evidence_staging_path=str(temp_staging),
        max_evidence_size_gb=1,
    )


@pytest.fixture(autouse=True)
def mock_pipeline_task_settings(pipeline_settings: Settings):
    """Ensure Celery task in integration pipeline uses pipeline_settings."""
    with patch("iryx.evidence.tasks.get_settings", return_value=pipeline_settings):
        yield pipeline_settings


@pytest.fixture
def db_engine():
    """Isolated SQLite database engine for pipeline integration tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def session_factory(db_engine):
    """Sessionmaker bound to pipeline database engine."""
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False)


@pytest.fixture
def db_session(session_factory) -> Generator[Session, None, None]:
    """Yield a database session and close."""
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def pipeline_setup(db_session: Session) -> dict[str, object]:
    """Create test organization, analyst user, and case."""
    user_svc = UserService(db_session)
    org_svc = OrganizationService(db_session)

    analyst = user_svc.create_user(
        UserCreate(email="lead_analyst@soc.iryx", password="Password123!")
    )
    org = org_svc.create_organization(name="DFIR SOC Team", creator_id=analyst.id)

    case = Case(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Dossier Pipeline Integration",
        status="open",
        description="Investigation bout-en-bout du pipeline d'ingestion",
        created_by=analyst.id,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    return {
        "org": org,
        "analyst": analyst,
        "case": case,
    }


def create_upload_file(filename: str, content: bytes) -> UploadFile:
    """Helper creating FastAPI UploadFile instance."""
    headers = Headers({"content-type": "application/octet-stream"})
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
        headers=headers,
    )


@pytest.mark.asyncio
async def test_evidence_ingestion_pipeline_nominal(
    pipeline_setup: dict[str, object],
    db_session: Session,
    session_factory,
    pipeline_settings: Settings,
    temp_staging: Path,
) -> None:
    """End-to-end pipeline: upload -> pending run -> Celery task -> completed run & sealed."""
    case: Case = pipeline_setup["case"]  # type: ignore
    analyst: User = pipeline_setup["analyst"]  # type: ignore

    payload = b"Windows EVTX Log Records Header with 64KB multi-chunk content: " + (b"A" * 70000)
    expected_sha256 = hashlib.sha256(payload).hexdigest()
    upload = create_upload_file("Security.evtx", payload)

    # 1. Upload evidence via EvidenceService (intercepting celery.delay)
    dispatched_args: list[tuple[str, str]] = []

    def mock_delay(ev_id: str, path: str):
        dispatched_args.append((ev_id, path))

    with (
        patch("iryx.evidence.services.get_settings", return_value=pipeline_settings),
        patch("iryx.evidence.services.process_evidence_ingestion.delay", side_effect=mock_delay),
    ):
        service = EvidenceService(db_session)
        evidence, ingestion_run = await service.upload_evidence(
            case_id=case.id,
            file=upload,
            current_user_id=analyst.id,
        )

    # Verify upload stage results
    assert evidence.sha256 is None
    assert evidence.detected_type is None
    assert ingestion_run.status == IngestionStatus.PENDING
    assert ingestion_run.progress == 0
    assert len(dispatched_args) == 1

    ev_id_str, staging_path_str = dispatched_args[0]
    assert ev_id_str == str(evidence.id)
    assert Path(staging_path_str).exists()

    # 2. Execute Celery worker task synchronously
    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        task_result = process_evidence_ingestion(ev_id_str, staging_path_str)

    assert task_result["status"] == "completed"
    assert task_result["sha256"] == expected_sha256

    # 3. Verify final database state from a separate verification session
    verify_session = session_factory()
    try:
        final_evidence = verify_session.get(Evidence, evidence.id)
        assert final_evidence is not None
        assert final_evidence.sha256 == expected_sha256
        assert final_evidence.detected_type == "application/octet-stream"

        final_run = verify_session.get(IngestionRun, ingestion_run.id)
        assert final_run is not None
        assert final_run.status == IngestionStatus.COMPLETED
        assert final_run.progress == 100
        assert final_run.error_message is None
        assert final_run.completed_at is not None

        # 4. Verify file locking (NFR-SEC-01): 0440 read-only
        staged_file = Path(staging_path_str)
        assert staged_file.exists()
        with pytest.raises(PermissionError), open(staged_file, "wb") as f:
            f.write(b"Attempted overwrite")
    finally:
        verify_session.close()


@pytest.mark.asyncio
async def test_evidence_ingestion_pipeline_detected_type_png(
    pipeline_setup: dict[str, object],
    db_session: Session,
    session_factory,
    pipeline_settings: Settings,
) -> None:
    """Verify pipeline detects image/png MIME type and seals file."""
    case: Case = pipeline_setup["case"]  # type: ignore
    analyst: User = pipeline_setup["analyst"]  # type: ignore

    upload = create_upload_file("screenshot.png", PNG_BYTES)
    expected_sha256 = hashlib.sha256(PNG_BYTES).hexdigest()

    dispatched: list[tuple[str, str]] = []
    with (
        patch("iryx.evidence.services.get_settings", return_value=pipeline_settings),
        patch(
            "iryx.evidence.services.process_evidence_ingestion.delay",
            side_effect=lambda a, b: dispatched.append((a, b)),
        ),
    ):
        service = EvidenceService(db_session)
        evidence, _ = await service.upload_evidence(case.id, upload, analyst.id)

    ev_id, staging_path = dispatched[0]
    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        task_result = process_evidence_ingestion(ev_id, staging_path)

    assert task_result["status"] == "completed"
    assert task_result["detected_type"] == "image/png"
    assert task_result["sha256"] == expected_sha256

    verify_session = session_factory()
    try:
        updated = verify_session.get(Evidence, evidence.id)
        assert updated is not None
        assert updated.detected_type == "image/png"
        assert updated.sha256 == expected_sha256
    finally:
        verify_session.close()


@pytest.mark.asyncio
async def test_evidence_ingestion_pipeline_detected_type_zip(
    pipeline_setup: dict[str, object],
    db_session: Session,
    session_factory,
    pipeline_settings: Settings,
) -> None:
    """Verify pipeline detects application/zip MIME type and seals file."""
    case: Case = pipeline_setup["case"]  # type: ignore
    analyst: User = pipeline_setup["analyst"]  # type: ignore

    upload = create_upload_file("triage_archive.zip", ZIP_BYTES)
    expected_sha256 = hashlib.sha256(ZIP_BYTES).hexdigest()

    dispatched: list[tuple[str, str]] = []
    with (
        patch("iryx.evidence.services.get_settings", return_value=pipeline_settings),
        patch(
            "iryx.evidence.services.process_evidence_ingestion.delay",
            side_effect=lambda a, b: dispatched.append((a, b)),
        ),
    ):
        service = EvidenceService(db_session)
        evidence, _ = await service.upload_evidence(case.id, upload, analyst.id)

    ev_id, staging_path = dispatched[0]
    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        task_result = process_evidence_ingestion(ev_id, staging_path)

    assert task_result["status"] == "completed"
    assert task_result["detected_type"] == "application/zip"
    assert task_result["sha256"] == expected_sha256

    verify_session = session_factory()
    try:
        updated = verify_session.get(Evidence, evidence.id)
        assert updated is not None
        assert updated.detected_type == "application/zip"
        assert updated.sha256 == expected_sha256
    finally:
        verify_session.close()


@pytest.mark.asyncio
async def test_evidence_ingestion_pipeline_failure_when_staging_file_deleted(
    pipeline_setup: dict[str, object],
    db_session: Session,
    session_factory,
    pipeline_settings: Settings,
) -> None:
    """Verify pipeline transitions to FAILED when physical file is missing before ingestion."""
    case: Case = pipeline_setup["case"]  # type: ignore
    analyst: User = pipeline_setup["analyst"]  # type: ignore

    upload = create_upload_file("deleted_prematurely.bin", b"Data bytes")
    dispatched: list[tuple[str, str]] = []

    with (
        patch("iryx.evidence.services.get_settings", return_value=pipeline_settings),
        patch(
            "iryx.evidence.services.process_evidence_ingestion.delay",
            side_effect=lambda a, b: dispatched.append((a, b)),
        ),
    ):
        service = EvidenceService(db_session)
        evidence, ingestion_run = await service.upload_evidence(case.id, upload, analyst.id)

    ev_id, staging_path = dispatched[0]
    # Delete the physical staging file before task executes
    Path(staging_path).unlink(missing_ok=True)

    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        task_result = process_evidence_ingestion(ev_id, staging_path)

    assert task_result["status"] == "failed"

    verify_session = session_factory()
    try:
        final_run = verify_session.get(IngestionRun, ingestion_run.id)
        assert final_run is not None
        assert final_run.status == IngestionStatus.FAILED
        assert final_run.error_message is not None
        assert final_run.completed_at is not None

        final_evidence = verify_session.get(Evidence, evidence.id)
        assert final_evidence is not None
        assert final_evidence.sha256 is None
    finally:
        verify_session.close()


@pytest.mark.asyncio
async def test_evidence_ingestion_pipeline_homonym_handling(
    pipeline_setup: dict[str, object],
    db_session: Session,
    session_factory,
    pipeline_settings: Settings,
) -> None:
    """Verify pipeline processes two identically named uploads as independent sealed evidences."""
    case: Case = pipeline_setup["case"]  # type: ignore
    analyst: User = pipeline_setup["analyst"]  # type: ignore

    content_v1 = b"Payload Version 1: Initial triage dump"
    content_v2 = b"Payload Version 2: Secondary triage dump - modified"
    sha_v1 = hashlib.sha256(content_v1).hexdigest()
    sha_v2 = hashlib.sha256(content_v2).hexdigest()

    dispatched: list[tuple[str, str]] = []
    with (
        patch("iryx.evidence.services.get_settings", return_value=pipeline_settings),
        patch(
            "iryx.evidence.services.process_evidence_ingestion.delay",
            side_effect=lambda a, b: dispatched.append((a, b)),
        ),
    ):
        service = EvidenceService(db_session)
        # Upload 1
        ev1, run1 = await service.upload_evidence(
            case.id, create_upload_file("artifact.raw", content_v1), analyst.id
        )
        # Upload 2 (same filename)
        ev2, run2 = await service.upload_evidence(
            case.id, create_upload_file("artifact.raw", content_v2), analyst.id
        )

    assert ev1.id != ev2.id
    assert len(dispatched) == 2

    # Execute ingestion on both
    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        res1 = process_evidence_ingestion(dispatched[0][0], dispatched[0][1])
        res2 = process_evidence_ingestion(dispatched[1][0], dispatched[1][1])

    assert res1["status"] == "completed"
    assert res2["status"] == "completed"
    assert res1["sha256"] == sha_v1
    assert res2["sha256"] == sha_v2

    verify_session = session_factory()
    try:
        db_ev1 = verify_session.get(Evidence, ev1.id)
        db_ev2 = verify_session.get(Evidence, ev2.id)
        assert db_ev1 is not None and db_ev2 is not None
        assert db_ev1.sha256 == sha_v1
        assert db_ev2.sha256 == sha_v2
        assert db_ev1.original_name == "artifact.raw"
        assert db_ev2.original_name == "artifact.raw"

        # Verify physical files co-exist and are locked
        path1 = Path(dispatched[0][1])
        path2 = Path(dispatched[1][1])
        assert path1.exists() and path2.exists()
        with pytest.raises(PermissionError), open(path1, "wb") as f:
            f.write(b"fail")
        with pytest.raises(PermissionError), open(path2, "wb") as f:
            f.write(b"fail")
    finally:
        verify_session.close()
