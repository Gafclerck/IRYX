"""IRYX Audit Trail API router for immutable case audit consultation (Story 8.5)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from iryx.api.dependencies import get_db
from iryx.audit.schemas import AuditEventListResponse, AuditEventOut
from iryx.audit.services import AuditService
from iryx.auth.models import MembershipRole
from iryx.cases.dependencies import require_case_role
from iryx.cases.models import Case

router = APIRouter(tags=["Audit"])


@router.get(
    "/api/v1/cases/{case_id}/audit-trail",
    response_model=AuditEventListResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultation paginée de la piste d'audit d'un dossier",
    description=(
        "Retourne le journal d'audit immutable d'un dossier, trié par ordre chronologique "
        "déterministe (created_at ASC, id ASC), réservé aux rôles admin et investigator."
    ),
)
def list_audit_trail(
    case_id: uuid.UUID,
    _case: Annotated[
        Case,
        Depends(
            require_case_role(
                MembershipRole.ADMIN,
                MembershipRole.INVESTIGATOR,
            )
        ),
    ],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int,
        Query(ge=1, le=100, description="Nombre maximum d'événements par page."),
    ] = 100,
    offset: Annotated[
        int,
        Query(ge=0, description="Index de départ de pagination."),
    ] = 0,
) -> AuditEventListResponse:
    """Consult the immutable audit trail of one investigation case."""
    service = AuditService(db)
    items = service.list_events(case_id=case_id, limit=limit, offset=offset)
    total = service.count_events(case_id=case_id)
    has_more = (offset + len(items)) < total
    return AuditEventListResponse(
        items=[AuditEventOut.model_validate(item) for item in items],
        total=total,
        total_items=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )
