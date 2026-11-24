"""Evidence domain service handling staging upload, homonym detection, and persistence."""

import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iryx.core.config import get_settings
from iryx.core.exceptions import (
    EmptyFileException,
    EvidenceNotFoundInCaseException,
    PayloadTooLargeException,
    ValidationException,
)
from iryx.evidence.models import Evidence, IngestionRun, IngestionStatus
from iryx.evidence.schemas import EvidenceIngestionStatusResponse
from iryx.evidence.tasks import CHUNK_SIZE, process_evidence_ingestion

logger = logging.getLogger(__name__)


class EvidenceService:
    """Service encapsulating evidence upload streaming, homonym checks, and lifecycle."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    async def upload_evidence(
        self,
        case_id: uuid.UUID,
        file: UploadFile,
        current_user_id: uuid.UUID,
    ) -> tuple[Evidence, IngestionRun]:
        """Stream uploaded file to unique staging path, detect homonyms, and queue ingestion.

        Args:
            case_id: Target investigation case UUID.
            file: Incoming FastAPI UploadFile multipart stream.
            current_user_id: Authenticated user initiating upload.

        Returns:
            Tuple of persisted (Evidence, IngestionRun) records.

        Raises:
            EmptyFileException: If uploaded stream has 0 bytes.
            PayloadTooLargeException: If upload exceeds configured max size.
            ValidationException: If original filename exceeds 255 characters.
        """
        raw_name = (file.filename or "").strip()
        cleaned_name = raw_name.replace("\\", "/").rstrip("/")
        basename = cleaned_name.rsplit("/", 1)[-1].strip()
        original_name = basename if basename else "evidence.bin"

        if len(original_name) > 255:
            raise ValidationException("Le nom du fichier ne doit pas dépasser 255 caractères.")

        new_evidence_id = uuid.uuid4()
        staging_dir = Path(self.settings.evidence_staging_path)
        staging_dir.mkdir(parents=True, exist_ok=True)
        staging_file_path = staging_dir / f"{new_evidence_id}.bin"

        max_bytes = self.settings.max_evidence_size_gb * 1024 * 1024 * 1024
        total_bytes = 0
        staging_committed = False

        try:
            # Stream chunks to disk to prevent RAM exhaustion (ADR-0005)
            try:
                with open(staging_file_path, "wb") as destination:
                    while chunk := await file.read(CHUNK_SIZE):
                        total_bytes += len(chunk)
                        if total_bytes > max_bytes:
                            raise PayloadTooLargeException()
                        destination.write(chunk)
            finally:
                await file.close()

            # Enforce non-empty payload requirement
            if total_bytes == 0:
                raise EmptyFileException()

            # Homonym detection: search for identical original_name in the same case
            existing_evidence = self.db.scalars(
                select(Evidence).where(
                    Evidence.case_id == case_id,
                    Evidence.original_name == original_name,
                )
            ).all()

            if existing_evidence:
                logger.warning(
                    "Téléversement d'une preuve homonyme dans le dossier",
                    extra={
                        "context": {
                            "case_id": str(case_id),
                            "original_name": original_name,
                            "new_evidence_id": str(new_evidence_id),
                            "conflicting_evidence_ids": [str(e.id) for e in existing_evidence],
                        }
                    },
                )

            now = datetime.now(UTC)
            evidence = Evidence(
                id=new_evidence_id,
                case_id=case_id,
                original_name=original_name,
                file_size=total_bytes,
                sha256=None,
                detected_type=None,
                imported_by=current_user_id,
                created_at=now,
            )
            ingestion_run = IngestionRun(
                evidence_id=new_evidence_id,
                status=IngestionStatus.PENDING,
                progress=0,
                error_message=None,
                started_at=now,
                completed_at=None,
            )

            try:
                self.db.add(evidence)
                self.db.add(ingestion_run)
                self.db.commit()
                self.db.refresh(evidence)
                self.db.refresh(ingestion_run)
                staging_committed = True
            except Exception:
                self.db.rollback()
                raise
        finally:
            if not staging_committed and staging_file_path.exists():
                staging_file_path.unlink(missing_ok=True)

        # Dispatch background Celery task
        try:
            process_evidence_ingestion.delay(str(evidence.id), str(staging_file_path))
        except Exception as exc:
            logger.error(
                "Échec de publication de la tâche Celery d'ingestion",
                extra={
                    "context": {
                        "evidence_id": str(evidence.id),
                        "staging_path": str(staging_file_path),
                        "error": str(exc),
                    }
                },
                exc_info=True,
            )
            ingestion_run.status = IngestionStatus.FAILED
            ingestion_run.error_message = str(exc)
            ingestion_run.completed_at = datetime.now(UTC)
            self.db.commit()

        return evidence, ingestion_run

    def get_evidence(self, case_id: uuid.UUID, evidence_id: uuid.UUID) -> Evidence:
        """Retrieve an evidence record guaranteeing it belongs to the given case.

        Args:
            case_id: Target investigation case UUID.
            evidence_id: Target evidence UUID.

        Returns:
            The matching Evidence entity.

        Raises:
            EvidenceNotFoundInCaseException: If evidence does not exist or does not belong to case.
        """
        evidence = self.db.scalar(
            select(Evidence).where(
                Evidence.id == evidence_id,
                Evidence.case_id == case_id,
            )
        )
        if evidence is None:
            raise EvidenceNotFoundInCaseException()
        return evidence

    def get_ingestion_status(
        self, case_id: uuid.UUID, evidence_id: uuid.UUID
    ) -> EvidenceIngestionStatusResponse:
        """Retrieve latest ingestion run status and sealed metadata for an evidence.

        Args:
            case_id: Target investigation case UUID.
            evidence_id: Target evidence UUID.

        Returns:
            EvidenceIngestionStatusResponse containing status, progress, error_message, sha256,
            and detected_type.

        Raises:
            EvidenceNotFoundInCaseException: If evidence does not exist or does not belong to case.
        """
        evidence = self.get_evidence(case_id=case_id, evidence_id=evidence_id)
        latest_run = self.db.scalar(
            select(IngestionRun)
            .where(IngestionRun.evidence_id == evidence_id)
            .order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc())
            .limit(1)
        )

        if (
            latest_run
            and latest_run.status == IngestionStatus.COMPLETED
            and evidence.sha256 is None
        ):
            self.db.refresh(evidence)

        sha256 = (
            evidence.sha256
            if (latest_run and latest_run.status == IngestionStatus.COMPLETED)
            else None
        )
        detected_type = (
            evidence.detected_type
            if (latest_run and latest_run.status == IngestionStatus.COMPLETED)
            else None
        )

        if latest_run is not None:
            return EvidenceIngestionStatusResponse(
                status=latest_run.status,
                progress=latest_run.progress,
                error_message=latest_run.error_message,
                sha256=sha256,
                detected_type=detected_type,
            )

        return EvidenceIngestionStatusResponse(
            status=IngestionStatus.PENDING,
            progress=0,
            error_message=None,
            sha256=None,
            detected_type=None,
        )

    def list_evidences(
        self, case_id: uuid.UUID, limit: int = 50, offset: int = 0
    ) -> tuple[list[Evidence], int]:
        """List paginated evidences for a case with deterministic ordering.

        Enforces deterministic ordering by created_at DESC, id DESC.

        Args:
            case_id: Target investigation case UUID.
            limit: Maximum items to return (1 <= limit <= 100).
            offset: Number of items to skip (offset >= 0).

        Returns:
            Tuple of (list of Evidence entities, total count of evidences for case).

        Raises:
            ValidationException: If limit < 1 or limit > 100 or offset < 0.
        """
        if limit < 1 or limit > 100 or offset < 0:
            raise ValidationException(
                "Les paramètres de pagination sont invalides (1 <= limit <= 100, offset >= 0)."
            )

        count_stmt = select(func.count(Evidence.id)).where(Evidence.case_id == case_id)
        total = self.db.scalar(count_stmt) or 0

        if total == 0 or offset >= total:
            return [], total

        stmt = (
            select(Evidence)
            .where(Evidence.case_id == case_id)
            .order_by(Evidence.created_at.desc(), Evidence.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = list(self.db.scalars(stmt).all())
        return items, total
