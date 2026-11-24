"""IRYX Evidence API Router exposing upload, polling, and pagination endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from iryx.api.dependencies import get_db
from iryx.auth.dependencies import get_current_user
from iryx.auth.models import User
from iryx.cases.dependencies import verify_case_access
from iryx.cases.models import Case
from iryx.evidence.models import IngestionStatus
from iryx.evidence.schemas import (
    EvidenceIngestionStatusResponse,
    EvidenceListResponse,
    EvidenceRead,
    EvidenceUploadResponse,
)
from iryx.evidence.services import EvidenceService

router = APIRouter(tags=["Evidences"])


@router.post(
    "/api/v1/cases/{case_id}/evidences",
    response_model=EvidenceUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Téléversement d'une preuve numérique",
    description=(
        "Téléverse un fichier de preuve en multipart, le diffuse par morceaux de 64 Ko "
        "vers le répertoire de staging sous un UUID unique, crée les entités Evidence et "
        "IngestionRun, et déclenche la tâche d'ingestion asynchrone."
    ),
)
async def upload_evidence(
    case_id: uuid.UUID,
    response: Response,
    file: Annotated[UploadFile, File(description="Fichier binaire de la preuve numérique")],
    _case: Annotated[Case, Depends(verify_case_access)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceUploadResponse:
    """Upload digital evidence for an investigation case."""
    evidence_service = EvidenceService(db)
    evidence, ingestion_run = await evidence_service.upload_evidence(
        case_id=case_id,
        file=file,
        current_user_id=current_user.id,
    )

    response.headers["Location"] = (
        f"/api/v1/cases/{case_id}/evidences/{evidence.id}/ingestion-status"
    )
    response.headers["Retry-After"] = "3"

    return EvidenceUploadResponse(
        evidence_id=evidence.id,
        ingestion_run_id=ingestion_run.id,
    )


@router.get(
    "/api/v1/cases/{case_id}/evidences/{evidence_id}/ingestion-status",
    response_model=EvidenceIngestionStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultation de l'état d'ingestion d'une preuve",
    description=(
        "Interroge l'état du dernier cycle d'ingestion et renvoie les métadonnées scellées. "
        "En cas de traitement en cours, renvoie l'en-tête Retry-After: 3."
    ),
)
def get_ingestion_status(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    response: Response,
    _case: Annotated[Case, Depends(verify_case_access)],
    _current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceIngestionStatusResponse:
    """Poll ingestion status and sealed cryptographic attributes."""
    service = EvidenceService(db)
    result = service.get_ingestion_status(case_id=case_id, evidence_id=evidence_id)
    if result.status in (IngestionStatus.PENDING, IngestionStatus.PROCESSING):
        response.headers["Retry-After"] = "3"
    return result


@router.get(
    "/api/v1/cases/{case_id}/evidences",
    response_model=EvidenceListResponse,
    status_code=status.HTTP_200_OK,
    summary="Liste paginée des preuves d'un dossier",
    description=(
        "Retourne la liste paginée des preuves numériques rattachées à un dossier. "
        "Tri déterministe (created_at DESC, id DESC), limit par défaut à 50 (max 100)."
    ),
)
def list_evidences(
    case_id: uuid.UUID,
    _case: Annotated[Case, Depends(verify_case_access)],
    _current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int, Query(ge=1, le=100, description="Nombre maximum de preuves par page.")
    ] = 50,
    offset: Annotated[int, Query(ge=0, description="Index de départ de pagination.")] = 0,
) -> EvidenceListResponse:
    """List paginated evidences for an investigation case."""
    service = EvidenceService(db)
    items, total = service.list_evidences(case_id=case_id, limit=limit, offset=offset)
    has_more = bool(items) and ((offset + len(items)) < total)
    return EvidenceListResponse(
        items=[EvidenceRead.model_validate(item) for item in items],
        total=total,
        total_items=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get(
    "/api/v1/cases/{case_id}/evidences/{evidence_id}",
    response_model=EvidenceRead,
    status_code=status.HTTP_200_OK,
    summary="Consultation des métadonnées d'une preuve",
    description=(
        "Retourne les métadonnées complètes d'une preuve numérique rattachée à un dossier."
    ),
)
def get_evidence(
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    _case: Annotated[Case, Depends(verify_case_access)],
    _current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> EvidenceRead:
    """Retrieve full metadata for a specific evidence within a case."""
    service = EvidenceService(db)
    evidence = service.get_evidence(case_id=case_id, evidence_id=evidence_id)
    return EvidenceRead.model_validate(evidence)
