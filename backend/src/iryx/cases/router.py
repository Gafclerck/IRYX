"""IRYX Cases and Investigation API Router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from iryx.api.dependencies import get_db
from iryx.auth.dependencies import get_current_user
from iryx.auth.models import Membership, MembershipRole, User
from iryx.cases.schemas import (
    CaseCreate,
    CaseListResponse,
    CaseOut,
    CaseStatusUpdate,
)
from iryx.cases.services import CaseService
from iryx.organizations.dependencies import require_role, verify_org_membership

router = APIRouter(tags=["Cases"])


@router.post(
    "/api/v1/organizations/{org_id}/cases",
    response_model=CaseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Création d'un dossier d'investigation",
    description=(
        "Crée un nouveau dossier au statut 'open' pour l'organisation spécifiée. "
        "Réservé aux membres ayant un rôle opérationnel ('admin', 'investigator', 'analyst')."
    ),
)
def create_case(
    org_id: uuid.UUID,
    payload: CaseCreate,
    _membership: Annotated[
        Membership,
        Depends(
            require_role(
                MembershipRole.ADMIN,
                MembershipRole.INVESTIGATOR,
                MembershipRole.ANALYST,
            )
        ),
    ],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CaseOut:
    """Create a new case within an organization."""
    service = CaseService(db)
    case = service.create_case(
        org_id=org_id,
        title=payload.title,
        description=payload.description,
        creator_id=current_user.id,
    )
    return CaseOut.model_validate(case)


@router.get(
    "/api/v1/organizations/{org_id}/cases",
    response_model=CaseListResponse,
    status_code=status.HTTP_200_OK,
    summary="Liste paginée des dossiers d'une organisation",
    description=(
        "Retourne la liste paginée des dossiers appartenant à l'organisation détentrice. "
        "Accessible à tout membre actif (y compris 'viewer')."
    ),
)
def list_cases(
    org_id: uuid.UUID,
    _membership: Annotated[Membership, Depends(verify_org_membership)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int, Query(ge=1, le=100, description="Nombre maximum de dossiers par page.")
    ] = 20,
    offset: Annotated[int, Query(ge=0, description="Index de départ de pagination.")] = 0,
) -> CaseListResponse:
    """List cases for an organization with pagination."""
    service = CaseService(db)
    items, total = service.list_cases(org_id=org_id, limit=limit, offset=offset)
    has_more = (offset + len(items)) < total
    return CaseListResponse(
        items=[CaseOut.model_validate(item) for item in items],
        total=total,
        total_items=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get(
    "/api/v1/cases/{case_id}",
    response_model=CaseOut,
    status_code=status.HTTP_200_OK,
    summary="Consultation unitaire d'un dossier",
    description=(
        "Retourne le détail d'un dossier si l'utilisateur est membre de l'organisation détentrice."
    ),
)
def get_case(
    case_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CaseOut:
    """Retrieve case details enforcing tenant membership."""
    service = CaseService(db)
    case = service.get_case_by_id(case_id=case_id, user_id=current_user.id)
    return CaseOut.model_validate(case)


@router.patch(
    "/api/v1/cases/{case_id}/status",
    response_model=CaseOut,
    status_code=status.HTTP_200_OK,
    summary="Mise à jour du statut opérationnel d'un dossier",
    description=(
        "Fait progresser le dossier dans son cycle de vie selon la matrice de transition stricte. "
        "Réservé aux membres habilités (hors rôle 'viewer')."
    ),
)
def update_case_status(
    case_id: uuid.UUID,
    payload: CaseStatusUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CaseOut:
    """Update case lifecycle status."""
    service = CaseService(db)
    case = service.update_case_status(
        case_id=case_id,
        new_status=payload.status,
        user_id=current_user.id,
    )
    return CaseOut.model_validate(case)
