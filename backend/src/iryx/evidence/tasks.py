"""Celery tasks for evidence ingestion processing."""

import logging

from iryx.core.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="iryx.evidence.tasks.process_evidence_ingestion")
def process_evidence_ingestion(evidence_id: str, staging_path: str) -> dict[str, str]:
    """Background Celery task processing evidence ingestion (stub for Story 3.3)."""
    logger.info(
        "Démarrage du traitement d'ingestion pour la preuve",
        extra={
            "context": {
                "evidence_id": evidence_id,
                "staging_path": staging_path,
            }
        },
    )
    return {"evidence_id": evidence_id, "status": "processing"}
