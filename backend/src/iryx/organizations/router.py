"""IRYX Organizations and RBAC Management API Router."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from iryx.api.dependencies import get_db
from iryx.auth.dependencies import get_current_user
from iryx.auth.models import Membership, User
from iryx.auth.schemas import OrganizationCreate, OrganizationResponse
from iryx.organizations.dependencies import require_role, verify_org_membership
from iryx.organizations.schemas import (
    MemberAddRequest,
    MemberListResponse,
    MemberOut,
    MemberUpdateRequest,
    OrganizationListResponse,
)
from iryx.organizations.services import OrganizationService

router = APIRouter(prefix="/api/v1/organizations", tags=["Organizations"])


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Création d'une organisation",
    description=(
        "Crée une nouvelle organisation et attribue automatiquement le rôle admin au créateur."
    ),
)
def create_organization(
    payload: OrganizationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OrganizationResponse:
    """Create an organization with the authenticated user automatically assigned as admin."""
    service = OrganizationService(db)
    org = service.create_organization(name=payload.name, creator_id=current_user.id)
    return OrganizationResponse.model_validate(org)


@router.get(
    "",
    response_model=OrganizationListResponse,
    status_code=status.HTTP_200_OK,
    summary="Liste des organisations de l'utilisateur",
    description="Retourne la liste paginée des organisations dont l'utilisateur est membre.",
)
def list_organizations(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int, Query(ge=1, le=100, description="Nombre maximum d'éléments par page.")
    ] = 20,
    offset: Annotated[int, Query(ge=0, description="Index de départ de pagination.")] = 0,
) -> OrganizationListResponse:
    """List organizations where the current user is a member with pagination."""
    service = OrganizationService(db)
    items, total = service.list_user_organizations(
        user_id=current_user.id, limit=limit, offset=offset
    )
    has_more = (offset + len(items)) < total
    return OrganizationListResponse(
        items=[OrganizationResponse.model_validate(item) for item in items],
        total=total,
        total_items=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.get(
    "/{org_id}",
    response_model=OrganizationResponse,
    status_code=status.HTTP_200_OK,
    summary="Consultation d'une organisation",
    description="Retourne les détails d'une organisation si membre (Zero Leak).",
)
def get_organization(
    org_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> OrganizationResponse:
    """Retrieve organization details enforcing zero-leak isolation."""
    service = OrganizationService(db)
    org = service.get_organization_by_id(org_id=org_id, user_id=current_user.id)
    return OrganizationResponse.model_validate(org)


@router.get(
    "/{org_id}/members",
    response_model=MemberListResponse,
    status_code=status.HTTP_200_OK,
    summary="Liste paginée des membres d'une organisation",
    description="Retourne la liste des membres pour un utilisateur membre de l'organisation.",
)
def list_members(
    org_id: uuid.UUID,
    _membership: Annotated[Membership, Depends(verify_org_membership)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[
        int, Query(ge=1, le=100, description="Nombre maximum d'éléments par page.")
    ] = 20,
    offset: Annotated[int, Query(ge=0, description="Index de départ de pagination.")] = 0,
) -> MemberListResponse:
    """List members of an organization with pagination."""
    service = OrganizationService(db)
    items, total = service.list_members(org_id=org_id, limit=limit, offset=offset)
    has_more = (offset + len(items)) < total
    return MemberListResponse(
        items=[MemberOut.model_validate(item) for item in items],
        total=total,
        total_items=total,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )


@router.post(
    "/{org_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ajout d'un membre à l'organisation",
    description=(
        "Ajoute un utilisateur existant à l'organisation avec un rôle spécifique. "
        "Réservé aux administrateurs."
    ),
)
def add_member(
    org_id: uuid.UUID,
    payload: MemberAddRequest,
    _admin_membership: Annotated[Membership, Depends(require_role("admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> MemberOut:
    """Add a member to an organization (Admin only)."""
    service = OrganizationService(db)
    membership = service.add_member(
        org_id=org_id,
        user_id=payload.user_id,
        role=payload.role,
    )
    return MemberOut.model_validate(membership)


@router.patch(
    "/{org_id}/members/{user_id}",
    response_model=MemberOut,
    status_code=status.HTTP_200_OK,
    summary="Modification du rôle d'un membre",
    description="Modifie le rôle d'un membre existant. Réservé aux administrateurs.",
)
def update_member_role(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: MemberUpdateRequest,
    _admin_membership: Annotated[Membership, Depends(require_role("admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> MemberOut:
    """Update role for an organization member (Admin only)."""
    service = OrganizationService(db)
    membership = service.update_member_role(
        org_id=org_id,
        target_user_id=user_id,
        new_role=payload.role,
    )
    return MemberOut.model_validate(membership)


@router.delete(
    "/{org_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Révocation d'un membre de l'organisation",
    description="Supprime un membre de l'organisation. Réservé aux administrateurs.",
)
def remove_member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    _admin_membership: Annotated[Membership, Depends(require_role("admin"))],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Remove a member from an organization (Admin only)."""
    service = OrganizationService(db)
    service.remove_member(
        org_id=org_id,
        target_user_id=user_id,
    )
