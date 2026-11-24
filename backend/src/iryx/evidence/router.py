"""IRYX Evidence API Router exposing upload and status endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from iryx.api.dependencies import get_db
from iryx.auth.dependencies import get_current_user
from iryx.auth.models import User
from iryx.cases.dependencies import verify_case_access
from iryx.cases.models import Case
from iryx.evidence.schemas import EvidenceUploadResponse
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

    return EvidenceUploadResponse(
        evidence_id=evidence.id,
        ingestion_run_id=ingestion_run.id,
    )
