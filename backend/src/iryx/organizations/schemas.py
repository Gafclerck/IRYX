"""IRYX Organization and Membership Pydantic Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from iryx.auth.models import MembershipRole
from iryx.auth.schemas import OrganizationCreate, OrganizationResponse

__all__ = [
    "MemberAddRequest",
    "MemberListResponse",
    "MemberOut",
    "MemberUpdateRequest",
    "OrganizationCreate",
    "OrganizationListResponse",
    "OrganizationResponse",
]


class MemberAddRequest(BaseModel):
    """Schema for adding a member to an organization."""

    user_id: uuid.UUID = Field(
        ...,
        description="Identifiant UUID de l'utilisateur à associer.",
    )
    role: MembershipRole = Field(
        ...,
        description="Rôle attribué ('admin', 'analyst', 'investigator', 'viewer').",
    )


class MemberUpdateRequest(BaseModel):
    """Schema for updating an existing member's role."""

    role: MembershipRole = Field(
        ...,
        description="Nouveau rôle attribué ('admin', 'analyst', 'investigator', 'viewer').",
    )


class MemberOut(BaseModel):
    """Public representation of an organization membership with member details."""

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    email: str | None = None
    role: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationListResponse(BaseModel):
    """Paginated collection of organizations."""

    items: list[OrganizationResponse]
    total: int
    total_items: int
    limit: int
    offset: int
    has_more: bool


class MemberListResponse(BaseModel):
    """Paginated collection of organization members."""

    items: list[MemberOut]
    total: int
    total_items: int
    limit: int
    offset: int
    has_more: bool
