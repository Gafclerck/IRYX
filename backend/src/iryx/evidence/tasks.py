"""Celery tasks for evidence ingestion processing."""

import hashlib
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import filetype
from sqlalchemy import select

from iryx.core.celery_app import celery_app
from iryx.core.config import get_settings
from iryx.db.session import SessionLocal
from iryx.evidence.models import Evidence, IngestionRun, IngestionStatus

logger = logging.getLogger(__name__)

CHUNK_SIZE = 65536  # 64 KB buffer per ADR-0005, D-14


@celery_app.task(name="iryx.evidence.tasks.process_evidence_ingestion")
def process_evidence_ingestion(evidence_id: str, staging_path: str) -> dict[str, Any]:
    """Background Celery task processing evidence ingestion.

    Steps:
    1. Validate evidence_id UUID and retrieve Evidence and IngestionRun from database.
    2. Idempotence guard: if IngestionRun is COMPLETED and Evidence.sha256 exists, return.
    3. Validate staging_path is within configured evidence_staging_path.
    4. Transition IngestionRun status to 'processing' with progress = 20%.
    5. Seal physical staging file with strict read-only permissions (0o440) (NFR-SEC-01).
    6. Stream file to compute SHA-256 hash using 64 KB chunks (ADR-0005, D-14).
    7. Verify file size matches evidence.file_size.
    8. Detect binary filetype and MIME type using in-memory first chunk (D-15).
    9. Persist calculated hash, detected type, and mark IngestionRun 'completed' (100%).
    """
    logger.info(
        "Démarrage du traitement d'ingestion pour la preuve",
        extra={
            "context": {
                "evidence_id": evidence_id,
                "staging_path": staging_path,
            }
        },
    )

    db = SessionLocal()
    ingestion_run: IngestionRun | None = None
    try:
        try:
            parsed_id = uuid.UUID(evidence_id)
        except (ValueError, TypeError, AttributeError) as val_err:
            logger.error(
                "Identifiant de preuve invalide reçu pour la tâche d'ingestion",
                extra={
                    "context": {
                        "evidence_id": evidence_id,
                        "staging_path": staging_path,
                        "error": str(val_err),
                    }
                },
            )
            return {
                "evidence_id": evidence_id,
                "status": "failed",
                "error": f"Invalid UUID: {val_err}",
            }

        evidence = db.get(Evidence, parsed_id)
        if evidence is None:
            logger.error(
                "Preuve introuvable en base pour le traitement d'ingestion",
                extra={
                    "context": {
                        "evidence_id": evidence_id,
                        "staging_path": staging_path,
                    }
                },
            )
            return {
                "evidence_id": evidence_id,
                "status": "failed",
                "error": "Evidence not found",
            }

        ingestion_run = db.scalars(
            select(IngestionRun)
            .where(IngestionRun.evidence_id == parsed_id)
            .order_by(IngestionRun.started_at.desc())
        ).first()

        if ingestion_run is None:
            logger.error(
                "IngestionRun introuvable en base pour la preuve",
                extra={
                    "context": {
                        "evidence_id": evidence_id,
                        "staging_path": staging_path,
                    }
                },
            )
            return {
                "evidence_id": evidence_id,
                "status": "failed",
                "error": "IngestionRun not found",
            }

        # Idempotence guard: if already completed and sha256 sealed, return immediately
        if ingestion_run.status == IngestionStatus.COMPLETED and evidence.sha256 is not None:
            logger.info(
                "Preuve déjà ingérée et scellée, exécution idempotente",
                extra={
                    "context": {
                        "evidence_id": evidence_id,
                        "sha256": evidence.sha256,
                        "detected_type": evidence.detected_type,
                    }
                },
            )
            return {
                "evidence_id": evidence_id,
                "status": "completed",
                "sha256": evidence.sha256,
                "detected_type": evidence.detected_type,
            }

        # Validate staging path is contained within configured evidence_staging_path
        settings = get_settings()
        resolved_staging = Path(staging_path).resolve()
        allowed_staging_dir = Path(settings.evidence_staging_path).resolve()
        if not resolved_staging.is_relative_to(allowed_staging_dir):
            raise ValueError(
                f"Chemin de staging non autorisé ou hors périmètre: {staging_path} "
                f"(hors de {allowed_staging_dir})"
            )

        # Transition IngestionRun to processing (20%)
        ingestion_run.status = IngestionStatus.PROCESSING
        ingestion_run.progress = 20
        db.commit()
        db.refresh(ingestion_run)

        # 1. Apply strict read-only file lock (0o440, NFR-SEC-01) before streaming
        os.chmod(staging_path, 0o440)

        # 2. Compute SHA-256 hash by 64 KB streaming chunks (ADR-0005, D-14)
        sha256_hash = hashlib.sha256()
        total_bytes = 0
        first_chunk: bytes | None = None
        with open(staging_path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                if first_chunk is None:
                    first_chunk = chunk
                total_bytes += len(chunk)
                sha256_hash.update(chunk)
        calculated_sha256 = sha256_hash.hexdigest()

        # 3. Verify file size integrity
        if total_bytes != evidence.file_size:
            raise ValueError(
                f"Incohérence de taille de fichier: {total_bytes} octets lus sur le disque "
                f"vs {evidence.file_size} octets enregistrés pour la preuve."
            )

        # 4. Binary inspection via filetype from in-memory first chunk (D-15)
        kind = filetype.guess(first_chunk if first_chunk is not None else b"")
        detected_type = kind.mime if kind is not None else "application/octet-stream"

        # 5. Update Evidence & IngestionRun to completed (100%)
        evidence.sha256 = calculated_sha256
        evidence.detected_type = detected_type

        ingestion_run.status = IngestionStatus.COMPLETED
        ingestion_run.progress = 100
        ingestion_run.error_message = None
        ingestion_run.completed_at = datetime.now(UTC)

        db.commit()

        logger.info(
            "Traitement d'ingestion de la preuve finalisé avec succès",
            extra={
                "context": {
                    "evidence_id": evidence_id,
                    "sha256": calculated_sha256,
                    "detected_type": detected_type,
                    "staging_path": staging_path,
                }
            },
        )
        return {
            "evidence_id": evidence_id,
            "status": "completed",
            "sha256": calculated_sha256,
            "detected_type": detected_type,
        }

    except Exception as exc:
        logger.error(
            "Échec lors du traitement d'ingestion de la preuve",
            extra={
                "context": {
                    "evidence_id": evidence_id,
                    "staging_path": staging_path,
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                }
            },
            exc_info=True,
        )
        try:
            db.rollback()
            if ingestion_run is not None:
                ingestion_run.status = IngestionStatus.FAILED
                ingestion_run.error_message = str(exc)
                ingestion_run.completed_at = datetime.now(UTC)
                db.commit()
        except Exception as rollback_exc:
            logger.error(
                "Échec lors de la mise à jour de l'échec d'ingestion en base",
                extra={
                    "context": {
                        "evidence_id": evidence_id,
                        "error": str(rollback_exc),
                    }
                },
                exc_info=True,
            )
            db.rollback()

        return {
            "evidence_id": evidence_id,
            "status": "failed",
            "error": str(exc),
        }
    finally:
        db.close()
