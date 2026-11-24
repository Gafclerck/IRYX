"""Unit tests for EvidenceService, upload streaming, homonym handling, and Celery tasks."""

import io
import logging
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers

from iryx.auth.models import Organization, User
from iryx.cases.models import Case
from iryx.core.config import Settings
from iryx.core.exceptions import (
    EmptyFileException,
    PayloadTooLargeException,
    ValidationException,
)
from iryx.db.base import Base
from iryx.evidence.models import Evidence, IngestionStatus
from iryx.evidence.schemas import EvidenceUploadResponse
from iryx.evidence.services import CHUNK_SIZE, EvidenceService


@pytest.fixture
def temp_staging_dir():
    """Create a temporary directory for evidence staging during testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def mock_settings(temp_staging_dir: Path):
    """Provide Settings with isolated evidence staging path and test limits."""
    return Settings(
        secret_key="unit-test-secret-key-min-32-chars-long",
        evidence_storage_path=str(temp_staging_dir.parent),
        evidence_staging_path=str(temp_staging_dir),
        max_evidence_size_gb=1,
    )


@pytest.fixture
def db_session() -> Session:
    """In-memory SQLite database session for unit tests."""
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
def seeded_case(db_session: Session) -> tuple[Case, User]:
    """Create a persistent Case and User for evidence association."""
    user = User(
        id=uuid.uuid4(),
        email="forensic_analyst@soc.iryx",
        hashed_password="dummy_hash_value",
        is_active=True,
    )
    org = Organization(
        id=uuid.uuid4(),
        name="SOC IRYX Unit",
    )
    case = Case(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Incident Forensique Test",
        status="open",
        description="Dossier d'investigation pour tests unitaires",
        created_by=user.id,
    )
    db_session.add(user)
    db_session.add(org)
    db_session.add(case)
    db_session.commit()
    db_session.refresh(user)
    db_session.refresh(case)
    return case, user


def create_upload_file(filename: str, content: bytes) -> UploadFile:
    """Helper to construct a FastAPI UploadFile from raw bytes."""
    headers = Headers({"content-type": "application/octet-stream"})
    file_obj = io.BytesIO(content)
    return UploadFile(
        file=file_obj,
        filename=filename,
        headers=headers,
    )


@pytest.mark.asyncio
async def test_upload_evidence_nominal(
    db_session: Session,
    seeded_case: tuple[Case, User],
    mock_settings: Settings,
    temp_staging_dir: Path,
) -> None:
    """Verify nominal upload streams by chunks, persists entities, and dispatches Celery task."""
    case, user = seeded_case
    payload = b"X" * (CHUNK_SIZE * 2 + 1024)  # 2 full chunks + 1024 bytes
    upload = create_upload_file("memory_dump.raw", payload)
    upload.read = AsyncMock(wraps=upload.read)
    upload.close = AsyncMock(wraps=upload.close)

    with (
        patch("iryx.evidence.services.get_settings", return_value=mock_settings),
        patch("iryx.evidence.services.process_evidence_ingestion.delay") as mock_celery_delay,
    ):
        service = EvidenceService(db_session)
        evidence, ingestion_run = await service.upload_evidence(
            case_id=case.id,
            file=upload,
            current_user_id=user.id,
        )

        # Verify chunked streaming read was called with CHUNK_SIZE multiple times
        assert upload.read.call_count == 4  # 2 full + 1 partial + 1 EOF
        for call_args in upload.read.call_args_list:
            assert call_args.args == (CHUNK_SIZE,)

        # Verify upload file handle was explicitly closed
        upload.close.assert_awaited_once()

        # Verify Evidence entity
        assert isinstance(evidence.id, uuid.UUID)
        assert evidence.case_id == case.id
        assert evidence.original_name == "memory_dump.raw"
        assert evidence.file_size == len(payload)
        assert evidence.imported_by == user.id
        assert evidence.sha256 is None  # SHA-256 deferred to Celery (Story 3.3)

        # Verify IngestionRun entity
        assert isinstance(ingestion_run.id, uuid.UUID)
        assert ingestion_run.evidence_id == evidence.id
        assert ingestion_run.status == IngestionStatus.PENDING
        assert ingestion_run.progress == 0
        assert ingestion_run.completed_at is None

        # Verify Staging file on disk
        expected_staging_file = temp_staging_dir / f"{evidence.id}.bin"
        assert expected_staging_file.exists()
        assert expected_staging_file.read_bytes() == payload

        # Verify Celery task dispatch
        mock_celery_delay.assert_called_once_with(
            str(evidence.id),
            str(expected_staging_file),
        )


@pytest.mark.asyncio
async def test_upload_evidence_empty_file_rejected(
    db_session: Session,
    seeded_case: tuple[Case, User],
    mock_settings: Settings,
    temp_staging_dir: Path,
) -> None:
    """Verify empty file (0 bytes) raises EmptyFileException and cleans staging."""
    case, user = seeded_case
    upload = create_upload_file("empty.bin", b"")

    with patch("iryx.evidence.services.get_settings", return_value=mock_settings):
        service = EvidenceService(db_session)
        with pytest.raises(EmptyFileException) as exc_info:
            await service.upload_evidence(
                case_id=case.id,
                file=upload,
                current_user_id=user.id,
            )

        assert exc_info.value.code == "EMPTY_FILE_ERROR"
        assert exc_info.value.status_code == 400

        # Verify no orphan files remain in staging directory
        staged_files = list(temp_staging_dir.glob("*.bin"))
        assert len(staged_files) == 0

        # Verify no evidence was persisted
        evidences = db_session.query(Evidence).all()
        assert len(evidences) == 0


@pytest.mark.asyncio
async def test_upload_evidence_payload_too_large_rejected(
    db_session: Session,
    seeded_case: tuple[Case, User],
    temp_staging_dir: Path,
) -> None:
    """Verify exceeding max_evidence_size_gb raises PayloadTooLargeException and purges."""
    case, user = seeded_case
    small_settings = Settings(
        secret_key="unit-test-secret-key-min-32-chars-long",
        evidence_storage_path=str(temp_staging_dir.parent),
        evidence_staging_path=str(temp_staging_dir),
        max_evidence_size_gb=1,
    )

    upload = create_upload_file("oversized.iso", b"A" * 500)

    with (
        patch("iryx.evidence.services.get_settings", return_value=small_settings),
        patch.object(small_settings, "max_evidence_size_gb", 0),  # max_bytes = 0
    ):
        service = EvidenceService(db_session)
        with pytest.raises(PayloadTooLargeException) as exc_info:
            await service.upload_evidence(
                case_id=case.id,
                file=upload,
                current_user_id=user.id,
            )

        assert exc_info.value.code == "PAYLOAD_TOO_LARGE"
        assert exc_info.value.status_code == 413

        # Verify staging file was purged
        assert len(list(temp_staging_dir.glob("*.bin"))) == 0


@pytest.mark.asyncio
async def test_upload_evidence_homonym_creates_distinct_entity_and_logs_warning(
    db_session: Session,
    seeded_case: tuple[Case, User],
    mock_settings: Settings,
    temp_staging_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify homonym upload creates a separate Evidence entity and logs security warning."""
    case, user = seeded_case

    # First upload
    upload_1 = create_upload_file("security.evtx", b"First log content")
    with (
        patch("iryx.evidence.services.get_settings", return_value=mock_settings),
        patch("iryx.evidence.services.process_evidence_ingestion.delay"),
    ):
        service = EvidenceService(db_session)
        ev_1, _ = await service.upload_evidence(
            case_id=case.id,
            file=upload_1,
            current_user_id=user.id,
        )

    # Second upload with identical filename
    upload_2 = create_upload_file("security.evtx", b"Second log content - different version")
    with (
        patch("iryx.evidence.services.get_settings", return_value=mock_settings),
        patch("iryx.evidence.services.process_evidence_ingestion.delay"),
        caplog.at_level(logging.WARNING),
    ):
        ev_2, _ = await service.upload_evidence(
            case_id=case.id,
            file=upload_2,
            current_user_id=user.id,
        )

    # Invariants verification
    assert ev_1.id != ev_2.id
    assert ev_1.original_name == ev_2.original_name == "security.evtx"
    assert ev_1.file_size != ev_2.file_size

    # Verify both physical files exist without overwriting
    file_1 = temp_staging_dir / f"{ev_1.id}.bin"
    file_2 = temp_staging_dir / f"{ev_2.id}.bin"
    assert file_1.exists()
    assert file_2.exists()
    assert file_1.read_bytes() == b"First log content"
    assert file_2.read_bytes() == b"Second log content - different version"

    # Verify structured warning log including conflicting_evidence_ids
    warning_records = [
        r for r in caplog.records if "Téléversement d'une preuve homonyme" in r.message
    ]
    assert len(warning_records) >= 1
    record = warning_records[-1]
    assert hasattr(record, "context")
    assert record.context["case_id"] == str(case.id)
    assert record.context["original_name"] == "security.evtx"
    assert record.context["new_evidence_id"] == str(ev_2.id)
    assert record.context["conflicting_evidence_ids"] == [str(ev_1.id)]


@pytest.mark.asyncio
async def test_upload_evidence_db_rollback_cleans_staging(
    db_session: Session,
    seeded_case: tuple[Case, User],
    mock_settings: Settings,
    temp_staging_dir: Path,
) -> None:
    """Verify database commit failure rolls back and cleans up staging file."""
    case, user = seeded_case
    upload = create_upload_file("test.bin", b"Data bytes")

    with (
        patch("iryx.evidence.services.get_settings", return_value=mock_settings),
        patch.object(db_session, "commit", side_effect=RuntimeError("DB Commit Crash")),
    ):
        service = EvidenceService(db_session)
        with pytest.raises(RuntimeError, match="DB Commit Crash"):
            await service.upload_evidence(
                case_id=case.id,
                file=upload,
                current_user_id=user.id,
            )

        # Staging file should be deleted on DB failure
        assert len(list(temp_staging_dir.glob("*.bin"))) == 0


@pytest.mark.asyncio
async def test_upload_evidence_pre_commit_db_failure_cleans_staging(
    db_session: Session,
    seeded_case: tuple[Case, User],
    mock_settings: Settings,
    temp_staging_dir: Path,
) -> None:
    """Verify pre-commit DB error during homonym lookup cleans up staging file."""
    case, user = seeded_case
    upload = create_upload_file("pre_commit.bin", b"Some content")

    with (
        patch("iryx.evidence.services.get_settings", return_value=mock_settings),
        patch.object(db_session, "scalars", side_effect=RuntimeError("Homonym query failed")),
    ):
        service = EvidenceService(db_session)
        with pytest.raises(RuntimeError, match="Homonym query failed"):
            await service.upload_evidence(case.id, upload, user.id)

        assert len(list(temp_staging_dir.glob("*.bin"))) == 0


@pytest.mark.asyncio
async def test_upload_evidence_celery_dispatch_failure_marks_run_failed(
    db_session: Session,
    seeded_case: tuple[Case, User],
    mock_settings: Settings,
) -> None:
    """Verify Celery task failure marks IngestionRun as FAILED with error message."""
    case, user = seeded_case
    upload = create_upload_file("celery_fail.bin", b"Some valid bytes")

    with (
        patch("iryx.evidence.services.get_settings", return_value=mock_settings),
        patch(
            "iryx.evidence.services.process_evidence_ingestion.delay",
            side_effect=RuntimeError("Redis connection refused"),
        ),
    ):
        service = EvidenceService(db_session)
        evidence, ingestion_run = await service.upload_evidence(
            case_id=case.id,
            file=upload,
            current_user_id=user.id,
        )

        assert ingestion_run.status == IngestionStatus.FAILED
        assert "Redis connection refused" in (ingestion_run.error_message or "")
        assert ingestion_run.completed_at is not None

        # Verify DB was committed with failed state
        db_session.refresh(ingestion_run)
        assert ingestion_run.status == IngestionStatus.FAILED


@pytest.mark.asyncio
async def test_upload_evidence_filename_sanitization_and_validation(
    db_session: Session,
    seeded_case: tuple[Case, User],
    mock_settings: Settings,
) -> None:
    """Verify filename cleaning (backslashes, path traversal, empty fallback) and 255 limit."""
    case, user = seeded_case
    service = EvidenceService(db_session)

    with (
        patch("iryx.evidence.services.get_settings", return_value=mock_settings),
        patch("iryx.evidence.services.process_evidence_ingestion.delay"),
    ):
        # Windows path traversal
        u1 = create_upload_file(r"C:\Windows\Temp\..\evidence_win.raw", b"Content 1")
        ev1, _ = await service.upload_evidence(case.id, u1, user.id)
        assert ev1.original_name == "evidence_win.raw"

        # Empty / whitespace filename fallback
        u2 = create_upload_file("   ", b"Content 2")
        ev2, _ = await service.upload_evidence(case.id, u2, user.id)
        assert ev2.original_name == "evidence.bin"

        # Filename > 255 chars
        u3 = create_upload_file("a" * 256 + ".bin", b"Content 3")
        with pytest.raises(ValidationException):
            await service.upload_evidence(case.id, u3, user.id)


def test_evidence_upload_response_schema_serialization() -> None:
    """Verify EvidenceUploadResponse validates UUIDs and serializes cleanly."""
    ev_id = uuid.uuid4()
    run_id = uuid.uuid4()

    response = EvidenceUploadResponse(
        evidence_id=ev_id,
        ingestion_run_id=run_id,
    )
    assert response.evidence_id == ev_id
    assert response.ingestion_run_id == run_id

    dump = response.model_dump(mode="json")
    assert dump == {
        "evidence_id": str(ev_id),
        "ingestion_run_id": str(run_id),
    }
