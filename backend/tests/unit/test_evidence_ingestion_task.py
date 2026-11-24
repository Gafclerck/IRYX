"""Unit tests for Celery evidence ingestion task (Story 3.3)."""

import contextlib
import hashlib
import os
import stat
import tempfile
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.auth.models import Organization, User
from iryx.cases.models import Case
from iryx.core.config import Settings
from iryx.db.base import Base
from iryx.evidence.models import Evidence, IngestionRun, IngestionStatus
from iryx.evidence.services import CHUNK_SIZE
from iryx.evidence.tasks import process_evidence_ingestion

# Minimal valid PNG magic bytes
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
    b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory with guaranteed cleanup of read-only files."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        yield tmp_path
        # Reset file permissions to writeable before directory cleanup
        for f in tmp_path.glob("*"):
            with contextlib.suppress(Exception):
                os.chmod(f, stat.S_IWRITE | stat.S_IREAD)


@pytest.fixture(autouse=True)
def mock_task_settings(temp_dir: Path):
    """Ensure settings use the temporary directory as evidence_staging_path."""
    settings = Settings(
        secret_key="unit-test-secret-key-min-32-chars-long",
        evidence_storage_path=str(temp_dir.parent),
        evidence_staging_path=str(temp_dir),
        max_evidence_size_gb=1,
    )
    with patch("iryx.evidence.tasks.get_settings", return_value=settings):
        yield settings


@pytest.fixture
def db_engine():
    """Create in-memory SQLite engine with static pool for isolated unit tests."""
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
    """Sessionmaker bound to the unit test engine."""
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False)


@pytest.fixture
def db_session(session_factory) -> Generator[Session, None, None]:
    """Yield a database session and close cleanly."""
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def seeded_case_and_evidence(
    db_session: Session,
    temp_dir: Path,
) -> tuple[Evidence, IngestionRun, Path]:
    """Seed User, Org, Case, Evidence, and IngestionRun with an existing staging file."""
    user = User(
        id=uuid.uuid4(),
        email="forensic_analyst@soc.iryx",
        hashed_password="dummy_hash_value",
        is_active=True,
    )
    org = Organization(id=uuid.uuid4(), name="SOC IRYX Task Unit")
    case = Case(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Dossier Analyse Ingestion",
        status="open",
        description="Dossier pour tests unitaires de la tâche d'ingestion",
        created_by=user.id,
    )
    evidence_id = uuid.uuid4()
    payload = b"Z" * (CHUNK_SIZE * 2 + 1024)
    evidence = Evidence(
        id=evidence_id,
        case_id=case.id,
        original_name="memory_dump.raw",
        file_size=len(payload),
        sha256=None,
        detected_type=None,
        imported_by=user.id,
    )
    ingestion_run = IngestionRun(
        evidence_id=evidence_id,
        status=IngestionStatus.PENDING,
        progress=0,
        error_message=None,
        started_at=datetime.now(UTC),
        completed_at=None,
    )
    db_session.add(user)
    db_session.add(org)
    db_session.add(case)
    db_session.add(evidence)
    db_session.add(ingestion_run)
    db_session.commit()
    db_session.refresh(evidence)
    db_session.refresh(ingestion_run)

    # Create staging file on disk with > 64 KB content to test multi-chunk streaming
    staging_file = temp_dir / f"{evidence_id}.bin"
    staging_file.write_bytes(payload)

    return evidence, ingestion_run, staging_file


def test_process_evidence_ingestion_nominal(
    session_factory,
    seeded_case_and_evidence: tuple[Evidence, IngestionRun, Path],
) -> None:
    """Verify nominal ingestion calculates SHA-256, guesses MIME, locks 0440, and completes."""
    evidence, ingestion_run, staging_file = seeded_case_and_evidence
    payload = staging_file.read_bytes()
    expected_sha256 = hashlib.sha256(payload).hexdigest()

    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        result = process_evidence_ingestion(str(evidence.id), str(staging_file))

    # Verify task return dictionary
    assert result["status"] == "completed"
    assert result["evidence_id"] == str(evidence.id)
    assert result["sha256"] == expected_sha256
    assert result["detected_type"] == "application/octet-stream"

    # Verify database state
    verify_session = session_factory()
    try:
        updated_evidence = verify_session.get(Evidence, evidence.id)
        assert updated_evidence is not None
        assert updated_evidence.sha256 == expected_sha256
        assert updated_evidence.detected_type == "application/octet-stream"

        updated_run = verify_session.get(IngestionRun, ingestion_run.id)
        assert updated_run is not None
        assert updated_run.status == IngestionStatus.COMPLETED
        assert updated_run.progress == 100
        assert updated_run.error_message is None
        assert updated_run.completed_at is not None
    finally:
        verify_session.close()

    # Verify file is locked read-only (0440): write attempts raise PermissionError
    with pytest.raises(PermissionError), open(staging_file, "wb") as f:
        f.write(b"Malicious overwrite attempt")

    # Read access remains fully permitted
    with open(staging_file, "rb") as f:
        read_back = f.read()
    assert read_back == payload


def test_process_evidence_ingestion_chunked_streaming(
    session_factory,
    seeded_case_and_evidence: tuple[Evidence, IngestionRun, Path],
) -> None:
    """Verify SHA-256 computation reads iteratively in 64 KB chunks without f.read() whole file."""
    evidence, _, staging_file = seeded_case_and_evidence

    read_calls: list[int] = []
    original_open = open

    def monitored_open(file, mode="r", *args, **kwargs):
        handle = original_open(file, mode, *args, **kwargs)
        if "rb" in mode and str(file) == str(staging_file):
            original_read = handle.read

            def wrapped_read(size=-1):
                read_calls.append(size)
                return original_read(size)

            handle.read = wrapped_read
        return handle

    with (
        patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory),
        patch("builtins.open", side_effect=monitored_open),
    ):
        result = process_evidence_ingestion(str(evidence.id), str(staging_file))

    assert result["status"] == "completed"
    # Ensure that chunked read was called with CHUNK_SIZE (65536)
    assert CHUNK_SIZE in read_calls
    # Ensure unbounded read (size=-1 or None) was never called on the evidence file
    assert -1 not in read_calls
    assert None not in read_calls


def test_process_evidence_ingestion_known_mime_type_detection(
    session_factory,
    seeded_case_and_evidence: tuple[Evidence, IngestionRun, Path],
) -> None:
    """Verify filetype accurately detects binary header formats (PNG image)."""
    evidence, ingestion_run, staging_file = seeded_case_and_evidence

    # Overwrite staging file with PNG binary payload and update expected file_size
    staging_file.write_bytes(PNG_BYTES)
    expected_sha256 = hashlib.sha256(PNG_BYTES).hexdigest()

    setup_session = session_factory()
    try:
        ev = setup_session.get(Evidence, evidence.id)
        assert ev is not None
        ev.file_size = len(PNG_BYTES)
        setup_session.commit()
    finally:
        setup_session.close()

    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        result = process_evidence_ingestion(str(evidence.id), str(staging_file))

    assert result["status"] == "completed"
    assert result["sha256"] == expected_sha256
    assert result["detected_type"] == "image/png"

    verify_session = session_factory()
    try:
        updated_evidence = verify_session.get(Evidence, evidence.id)
        assert updated_evidence is not None
        assert updated_evidence.detected_type == "image/png"
        assert updated_evidence.sha256 == expected_sha256
    finally:
        verify_session.close()


def test_process_evidence_ingestion_unknown_mime_fallback(
    session_factory,
    seeded_case_and_evidence: tuple[Evidence, IngestionRun, Path],
) -> None:
    """Verify unknown binary or plain text gracefully falls back to application/octet-stream."""
    evidence, ingestion_run, staging_file = seeded_case_and_evidence
    plain_text = b"2026-11-24 10:00:00 [INFO] Authentication success user=analyst"
    staging_file.write_bytes(plain_text)

    setup_session = session_factory()
    try:
        ev = setup_session.get(Evidence, evidence.id)
        assert ev is not None
        ev.file_size = len(plain_text)
        setup_session.commit()
    finally:
        setup_session.close()

    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        result = process_evidence_ingestion(str(evidence.id), str(staging_file))

    assert result["status"] == "completed"
    assert result["detected_type"] == "application/octet-stream"

    verify_session = session_factory()
    try:
        updated_evidence = verify_session.get(Evidence, evidence.id)
        assert updated_evidence is not None
        assert updated_evidence.detected_type == "application/octet-stream"
    finally:
        verify_session.close()


def test_process_evidence_ingestion_missing_staging_file(
    session_factory,
    seeded_case_and_evidence: tuple[Evidence, IngestionRun, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify missing staging file marks IngestionRun as FAILED and logs structured error."""
    evidence, ingestion_run, staging_file = seeded_case_and_evidence

    # Remove staging file prior to task invocation
    staging_file.unlink(missing_ok=True)
    assert not staging_file.exists()

    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        result = process_evidence_ingestion(str(evidence.id), str(staging_file))

    assert result["status"] == "failed"
    assert "error" in result

    verify_session = session_factory()
    try:
        updated_run = verify_session.get(IngestionRun, ingestion_run.id)
        assert updated_run is not None
        assert updated_run.status == IngestionStatus.FAILED
        assert updated_run.error_message is not None
        assert updated_run.completed_at is not None

        # Evidence sha256 remains unsealed
        updated_evidence = verify_session.get(Evidence, evidence.id)
        assert updated_evidence is not None
        assert updated_evidence.sha256 is None
    finally:
        verify_session.close()

    # Verify structured ERROR log was emitted
    error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_logs) >= 1
    assert any(
        "Erreur lors de l'ingestion" in r.message or "Échec" in r.message for r in error_logs
    )


def test_process_evidence_ingestion_io_read_error(
    session_factory,
    seeded_case_and_evidence: tuple[Evidence, IngestionRun, Path],
) -> None:
    """Verify I/O read failure marks IngestionRun as FAILED without deleting physical file."""
    evidence, ingestion_run, staging_file = seeded_case_and_evidence
    assert staging_file.exists()

    mock_open_file = MagicMock()
    mock_open_file.__enter__.return_value.read.side_effect = OSError("Simulated Bad Sector I/O")

    with (
        patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory),
        patch("builtins.open", return_value=mock_open_file),
    ):
        result = process_evidence_ingestion(str(evidence.id), str(staging_file))

    assert result["status"] == "failed"
    assert "Simulated Bad Sector I/O" in result["error"]

    verify_session = session_factory()
    try:
        updated_run = verify_session.get(IngestionRun, ingestion_run.id)
        assert updated_run is not None
        assert updated_run.status == IngestionStatus.FAILED
        assert "Simulated Bad Sector I/O" in (updated_run.error_message or "")
    finally:
        verify_session.close()

    # Verify the physical file is NOT deleted or wiped (remains intact for forensics)
    assert staging_file.exists()


def test_process_evidence_ingestion_unknown_evidence_id(
    session_factory,
    temp_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify non-existent evidence_id logs error and aborts without unhandled crash."""
    random_id = str(uuid.uuid4())
    dummy_path = str(temp_dir / "dummy.bin")

    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        result = process_evidence_ingestion(random_id, dummy_path)

    assert result["status"] == "failed"
    assert result["error"] == "Evidence not found"

    error_logs = [
        r
        for r in caplog.records
        if "Preuve introuvable en base pour le traitement d'ingestion" in r.message
    ]
    assert len(error_logs) >= 1
    assert error_logs[0].context["evidence_id"] == random_id


def test_process_evidence_ingestion_invalid_uuid(
    session_factory,
    temp_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify malformed non-UUID evidence_id logs error and returns failed status."""
    invalid_id = "not-a-valid-uuid-string"
    dummy_path = str(temp_dir / "dummy.bin")

    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        result = process_evidence_ingestion(invalid_id, dummy_path)

    assert result["status"] == "failed"
    assert "Invalid UUID" in result["error"]

    error_logs = [
        r for r in caplog.records if "Identifiant de preuve invalide" in r.message
    ]
    assert len(error_logs) >= 1
    assert error_logs[0].context["evidence_id"] == invalid_id


def test_process_evidence_ingestion_chmod_failure(
    session_factory,
    seeded_case_and_evidence: tuple[Evidence, IngestionRun, Path],
) -> None:
    """Verify permission failure on os.chmod marks IngestionRun as FAILED."""
    evidence, ingestion_run, staging_file = seeded_case_and_evidence

    with (
        patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory),
        patch("os.chmod", side_effect=PermissionError("Permission denied on chmod")),
    ):
        result = process_evidence_ingestion(str(evidence.id), str(staging_file))

    assert result["status"] == "failed"
    assert "Permission denied on chmod" in result["error"]

    verify_session = session_factory()
    try:
        updated_run = verify_session.get(IngestionRun, ingestion_run.id)
        assert updated_run is not None
        assert updated_run.status == IngestionStatus.FAILED
        assert "Permission denied on chmod" in (updated_run.error_message or "")
    finally:
        verify_session.close()


def test_process_evidence_ingestion_transitions_to_processing_state_first(
    session_factory,
    seeded_case_and_evidence: tuple[Evidence, IngestionRun, Path],
) -> None:
    """Verify IngestionRun passes through processing (20%) prior to final completed state."""
    evidence, ingestion_run, staging_file = seeded_case_and_evidence
    statuses_seen: list[tuple[IngestionStatus, int]] = []

    real_session = session_factory()

    def wrapped_sessionmaker():
        session = session_factory()
        original_commit = session.commit

        def spy_commit():
            ret = original_commit()
            run = session.get(IngestionRun, ingestion_run.id)
            if run is not None:
                statuses_seen.append((run.status, run.progress))
            return ret

        session.commit = spy_commit
        return session

    with patch("iryx.evidence.tasks.SessionLocal", side_effect=wrapped_sessionmaker):
        result = process_evidence_ingestion(str(evidence.id), str(staging_file))

    real_session.close()
    assert result["status"] == "completed"
    # Must observe (processing, 20) committed before (completed, 100)
    assert (IngestionStatus.PROCESSING, 20) in statuses_seen
    assert (IngestionStatus.COMPLETED, 100) in statuses_seen


def test_process_evidence_ingestion_idempotence(
    session_factory,
    seeded_case_and_evidence: tuple[Evidence, IngestionRun, Path],
) -> None:
    """Verify task is idempotent: already COMPLETED run returns without re-processing."""
    evidence, ingestion_run, staging_file = seeded_case_and_evidence

    # Set up evidence and ingestion_run as already completed
    setup_session = session_factory()
    try:
        ev = setup_session.get(Evidence, evidence.id)
        run = setup_session.get(IngestionRun, ingestion_run.id)
        assert ev is not None and run is not None
        ev.sha256 = "already_computed_sha256_hash"
        ev.detected_type = "image/png"
        run.status = IngestionStatus.COMPLETED
        run.progress = 100
        run.completed_at = datetime.now(UTC)
        setup_session.commit()
    finally:
        setup_session.close()

    # Track if commit is ever called
    commits: list[str] = []

    def wrapped_sessionmaker():
        session = session_factory()
        original_commit = session.commit

        def spy_commit():
            commits.append("commit")
            return original_commit()

        session.commit = spy_commit
        return session

    with patch("iryx.evidence.tasks.SessionLocal", side_effect=wrapped_sessionmaker):
        result = process_evidence_ingestion(str(evidence.id), str(staging_file))

    assert result["status"] == "completed"
    assert result["sha256"] == "already_computed_sha256_hash"
    assert result["detected_type"] == "image/png"
    # Idempotent return should not perform any commits or state transitions
    assert len(commits) == 0


def test_process_evidence_ingestion_file_size_mismatch(
    session_factory,
    seeded_case_and_evidence: tuple[Evidence, IngestionRun, Path],
) -> None:
    """Verify integrity check raises error when streamed bytes differ from evidence.file_size."""
    evidence, ingestion_run, staging_file = seeded_case_and_evidence

    # Modify evidence.file_size to mismatch actual file bytes
    setup_session = session_factory()
    try:
        ev = setup_session.get(Evidence, evidence.id)
        assert ev is not None
        ev.file_size = 42  # actual file is CHUNK_SIZE * 2 + 1024
        setup_session.commit()
    finally:
        setup_session.close()

    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        result = process_evidence_ingestion(str(evidence.id), str(staging_file))

    assert result["status"] == "failed"
    assert "Incohérence de taille de fichier" in result["error"]

    verify_session = session_factory()
    try:
        updated_run = verify_session.get(IngestionRun, ingestion_run.id)
        assert updated_run is not None
        assert updated_run.status == IngestionStatus.FAILED
        assert "Incohérence de taille de fichier" in (updated_run.error_message or "")
    finally:
        verify_session.close()


def test_process_evidence_ingestion_missing_ingestion_run(
    session_factory,
    seeded_case_and_evidence: tuple[Evidence, IngestionRun, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify task returns failed status cleanly when IngestionRun record is missing."""
    evidence, ingestion_run, staging_file = seeded_case_and_evidence

    # Delete the IngestionRun from database
    delete_session = session_factory()
    try:
        run = delete_session.get(IngestionRun, ingestion_run.id)
        if run is not None:
            delete_session.delete(run)
            delete_session.commit()
    finally:
        delete_session.close()

    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        result = process_evidence_ingestion(str(evidence.id), str(staging_file))

    assert result["status"] == "failed"
    assert result["error"] == "IngestionRun not found"

    error_logs = [
        r for r in caplog.records if "IngestionRun introuvable" in r.message
    ]
    assert len(error_logs) >= 1
    assert error_logs[0].context["evidence_id"] == str(evidence.id)


def test_process_evidence_ingestion_staging_path_outside_allowed_dir(
    session_factory,
    seeded_case_and_evidence: tuple[Evidence, IngestionRun, Path],
) -> None:
    """Verify task rejects staging path outside configured evidence_staging_path."""
    evidence, ingestion_run, _ = seeded_case_and_evidence
    outside_path = "/tmp/malicious/unauthorized_path.bin"

    with patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory):
        result = process_evidence_ingestion(str(evidence.id), outside_path)

    assert result["status"] == "failed"
    assert "hors périmètre" in result["error"]

    verify_session = session_factory()
    try:
        updated_run = verify_session.get(IngestionRun, ingestion_run.id)
        assert updated_run is not None
        assert updated_run.status == IngestionStatus.FAILED
    finally:
        verify_session.close()
