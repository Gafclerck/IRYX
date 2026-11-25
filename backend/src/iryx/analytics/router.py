"""IRYX Analytics and Findings API Router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from iryx.analytics.models import (
    FindingConfidence,
    FindingSeverity,
    FindingStatus,
    FindingType,
)
from iryx.analytics.schemas import (
    FindingCreate,
    FindingListResponse,
    FindingOut,
    FindingUpdate,
)
from iryx.analytics.services import FindingService
from iryx.api.dependencies import get_db
from iryx.auth.dependencies import get_current_user
from iryx.auth.models import MembershipRole, User
from iryx.cases.dependencies import require_case_role, verify_case_access
from iryx.cases.models import Case

router = APIRouter(tags=["Findings"])


@router.post(
    "/api/v1/cases/{case_id}/findings",
    response_model=FindingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Création d'un constat d'investigation (Finding)",
    description=(
        "Crée un nouveau constat technique au statut initial 'proposed'. "
        "Exige un rôle opérationnel ('admin', 'investigator', 'analyst')."
    ),
)
def create_finding(
    case_id: uuid.UUID,
    payload: FindingCreate,
    _case: Annotated[
        Case,
        Depends(
            require_case_role(
                MembershipRole.ADMIN,
                MembershipRole.INVESTIGATOR,
                MembershipRole.ANALYST,
            )
        ),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FindingOut:
    """Create a new technical finding within an investigation case."""
    service = FindingService(db)
    finding = service.create_finding(
        case_id=case_id,
        payload=payload,
        created_by=current_user.id,
    )
    return FindingOut.model_validate(finding)


@router.get(
    "/api/v1/cases/{case_id}/findings",
    response_model=FindingListResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultation paginée des constats d'un dossier",
    description="Retourne la liste paginée des findings associés au dossier avec filtres.",
)
def list_findings(
    case_id: uuid.UUID,
    _case: Annotated[Case, Depends(verify_case_access)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100, description="Nombre maximum d'éléments")] = 50,
    offset: Annotated[int, Query(ge=0, description="Décalage pour pagination")] = 0,
    finding_status: Annotated[
        FindingStatus | None,
        Query(
            alias="status",
            description="Filtrer par statut ('proposed', 'validated', 'rejected')",
        ),
    ] = None,
    severity: Annotated[
        FindingSeverity | None,
        Query(description="Filtrer par sévérité ('low', 'medium', 'high', 'critical')"),
    ] = None,
    confidence: Annotated[
        FindingConfidence | None,
        Query(description="Filtrer par niveau de confiance ('low', 'medium', 'high')"),
    ] = None,
    finding_type: Annotated[
        FindingType | None,
        Query(description="Filtrer par type de constat ('fact', 'inference', 'hypothesis')"),
    ] = None,
) -> FindingListResponse:
    """List paginated findings in a case with filtering."""
    service = FindingService(db)
    items, total = service.list_findings(
        case_id=case_id,
        limit=limit,
        offset=offset,
        status=finding_status,
        severity=severity,
        confidence=confidence,
        finding_type=finding_type,
    )
    return FindingListResponse(
        items=[FindingOut.model_validate(item) for item in items],
        total=total,
        total_items=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(items)) < total,
    )


@router.get(
    "/api/v1/cases/{case_id}/findings/{finding_id}",
    response_model=FindingOut,
    status_code=status.HTTP_200_OK,
    summary="Détail d'un constat d'investigation",
    description="Récupère un constat par son identifiant unique et vérifie l'accès au dossier.",
)
def get_finding(
    case_id: uuid.UUID,
    finding_id: uuid.UUID,
    _case: Annotated[Case, Depends(verify_case_access)],
    db: Annotated[Session, Depends(get_db)],
) -> FindingOut:
    """Retrieve details of a single finding."""
    service = FindingService(db)
    finding = service.get_finding(case_id=case_id, finding_id=finding_id)
    return FindingOut.model_validate(finding)


@router.patch(
    "/api/v1/cases/{case_id}/findings/{finding_id}",
    response_model=FindingOut,
    status_code=status.HTTP_200_OK,
    summary="Mise à jour d'un constat d'investigation",
    description=(
        "Met à jour les attributs d'un constat existant. "
        "Exige un rôle opérationnel ('admin', 'investigator', 'analyst')."
    ),
)
def update_finding(
    case_id: uuid.UUID,
    finding_id: uuid.UUID,
    payload: FindingUpdate,
    _case: Annotated[
        Case,
        Depends(
            require_case_role(
                MembershipRole.ADMIN,
                MembershipRole.INVESTIGATOR,
                MembershipRole.ANALYST,
            )
        ),
    ],
    _current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FindingOut:
    """Update finding attributes."""
    service = FindingService(db)
    finding = service.update_finding(
        case_id=case_id,
        finding_id=finding_id,
        payload=payload,
    )
    return FindingOut.model_validate(finding)


@router.delete(
    "/api/v1/cases/{case_id}/findings/{finding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Suppression d'un constat d'investigation",
    description=(
        "Supprime définitivement un constat. "
        "Exige un rôle opérationnel ('admin', 'investigator', 'analyst')."
    ),
)
def delete_finding(
    case_id: uuid.UUID,
    finding_id: uuid.UUID,
    _case: Annotated[
        Case,
        Depends(
            require_case_role(
                MembershipRole.ADMIN,
                MembershipRole.INVESTIGATOR,
                MembershipRole.ANALYST,
            )
        ),
    ],
    _current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Delete a finding."""
    service = FindingService(db)
    service.delete_finding(case_id=case_id, finding_id=finding_id)
