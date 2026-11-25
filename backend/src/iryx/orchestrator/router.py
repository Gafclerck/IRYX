"""FastAPI router for Investigation Run orchestration endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from iryx.api.dependencies import get_db
from iryx.auth.dependencies import get_current_user
from iryx.auth.models import MembershipRole, User
from iryx.cases.dependencies import require_case_role, verify_case_access
from iryx.cases.models import Case
from iryx.orchestrator.schemas import (
    H1DecisionRequest,
    H1DecisionResponse,
    InvestigationPlan,
    InvestigationRunOut,
)
from iryx.orchestrator.services import InvestigationService

router = APIRouter(tags=["Orchestrator"])


@router.post(
    "/api/v1/cases/{case_id}/investigations",
    response_model=InvestigationRunOut,
    status_code=status.HTTP_201_CREATED,
    summary="Démarrage d'une session d'investigation",
    description=(
        "Démarre une nouvelle session d'investigation sur le dossier spécifié. "
        "Interdit si une session est déjà active ('pending', 'running', 'paused'). "
        "Réservé aux rôles ADMIN, INVESTIGATOR et ANALYST (interdit aux VIEWERS)."
    ),
)
def create_investigation(
    case_id: uuid.UUID,
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
    db: Annotated[Session, Depends(get_db)],
) -> InvestigationRunOut:
    """Create and start an investigation run for a case."""
    service = InvestigationService(db)
    return service.start_investigation(case_id=case_id)


@router.get(
    "/api/v1/cases/{case_id}/investigations",
    response_model=list[InvestigationRunOut],
    status_code=status.HTTP_200_OK,
    summary="Liste des sessions d'investigation d'un dossier",
    description="Récupère la liste de toutes les sessions d'investigation associées au dossier.",
)
def list_investigations(
    case_id: uuid.UUID,
    _case: Annotated[Case, Depends(verify_case_access)],
    db: Annotated[Session, Depends(get_db)],
) -> list[InvestigationRunOut]:
    """List all investigation runs for a case."""
    service = InvestigationService(db)
    return service.list_investigation_runs(case_id=case_id)


@router.get(
    "/api/v1/cases/{case_id}/investigations/{run_id}",
    response_model=InvestigationRunOut,
    status_code=status.HTTP_200_OK,
    summary="Consultation d'une session d'investigation",
    description=(
        "Récupère les détails, la phase active et les métadonnées "
        "d'une session d'investigation."
    ),
)
def get_investigation(
    case_id: uuid.UUID,
    run_id: uuid.UUID,
    _case: Annotated[Case, Depends(verify_case_access)],
    db: Annotated[Session, Depends(get_db)],
) -> InvestigationRunOut:
    """Retrieve investigation run details."""
    service = InvestigationService(db)
    return service.get_investigation_run(case_id=case_id, run_id=run_id)


@router.get(
    "/api/v1/cases/{case_id}/investigations/{run_id}/plan",
    response_model=InvestigationPlan,
    status_code=status.HTTP_200_OK,
    summary="Consultation du plan d'investigation",
    description=(
        "Récupère le plan d'actions forensiques proposé pour cette session d'investigation. "
        "Renvoie HTTP 404 PLAN_NOT_FOUND si aucun plan n'est encore associé."
    ),
)
def get_investigation_plan(
    case_id: uuid.UUID,
    run_id: uuid.UUID,
    _case: Annotated[Case, Depends(verify_case_access)],
    db: Annotated[Session, Depends(get_db)],
) -> InvestigationPlan:
    """Retrieve the investigation plan for a given run."""
    service = InvestigationService(db)
    return service.get_investigation_plan(case_id=case_id, run_id=run_id)


@router.post(
    "/api/v1/cases/{case_id}/investigations/{run_id}/gates/h1",
    response_model=H1DecisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Arbitrage de la porte de validation humaine H1",
    description=(
        "Permet à un analyste ou enquêteur d'approuver, de modifier ou de rejeter "
        "le plan d'investigation proposé par le Planner à la porte H1. "
        "Réservé aux rôles ADMIN, INVESTIGATOR et ANALYST (interdit aux VIEWERS)."
    ),
)
def arbitrate_gate_h1(
    case_id: uuid.UUID,
    run_id: uuid.UUID,
    payload: H1DecisionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
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
    db: Annotated[Session, Depends(get_db)],
) -> H1DecisionResponse:
    """Arbitrate the Human Gate H1 for an investigation run."""
    service = InvestigationService(db)
    return service.arbitrate_gate_h1(
        case_id=case_id,
        run_id=run_id,
        decision_request=payload,
        user_id=current_user.id,
    )

