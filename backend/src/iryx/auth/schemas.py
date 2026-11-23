"""IRYX Authentication and User Pydantic Schemas."""

import uuid
from datetime import datetime

import email_validator
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from iryx.auth.models import MembershipRole

# Allow .local domain for IRYX environment per architectural specifications
if "local" in email_validator.SPECIAL_USE_DOMAIN_NAMES:
    email_validator.SPECIAL_USE_DOMAIN_NAMES = [
        d for d in email_validator.SPECIAL_USE_DOMAIN_NAMES if d != "local"
    ]


class UserCreate(BaseModel):
    """Schema for user registration and account creation."""

    email: EmailStr = Field(
        ...,
        max_length=255,
        description="Adresse email de l'utilisateur (normalisée, max 255 caractères).",
    )
    password: str = Field(
        ...,
        min_length=12,
        max_length=128,
        description="Mot de passe d'au moins 12 caractères et maximum 128 caractères.",
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: object) -> object:
        """Strip leading/trailing whitespace and convert email to lowercase."""
        if isinstance(v, str):
            return v.strip().lower()
        return v


class UserResponse(BaseModel):
    """Public user representation excluding sensitive authentication credentials."""

    id: uuid.UUID
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    """Schema for user authentication and session opening request."""

    email: EmailStr = Field(
        ...,
        max_length=255,
        description="Adresse email de l'utilisateur.",
    )
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Mot de passe de l'utilisateur.",
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: object) -> object:
        """Strip leading/trailing whitespace and convert email to lowercase."""
        if isinstance(v, str):
            return v.strip().lower()
        return v


class TokenResponse(BaseModel):
    """Schema for successful authentication response containing JWT bearer token."""

    access_token: str = Field(..., description="Jeton d'accès JWT signé (HS256).")
    token_type: str = Field("bearer", description="Type de jeton (bearer).")
    expires_in: int = Field(..., description="Durée de validité du jeton en secondes (3600s).")


class OrganizationCreate(BaseModel):
    """Schema for organization registration and tenant creation."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Nom de l'organisation cliente ou équipe de sécurité.",
    )

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, v: object) -> object:
        """Strip leading and trailing whitespace from organization name."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("Organization name cannot be empty or whitespace only.")
        return v


class OrganizationResponse(BaseModel):
    """Public organization representation."""

    id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MembershipCreate(BaseModel):
    """Schema for adding a user to an organization with a specific RBAC role."""

    organization_id: uuid.UUID = Field(
        ...,
        description="Identifiant UUID de l'organisation.",
    )
    user_id: uuid.UUID = Field(
        ...,
        description="Identifiant UUID de l'utilisateur.",
    )
    role: MembershipRole = Field(
        ...,
        description="Rôle attribué ('admin', 'analyst', 'investigator', 'viewer').",
    )


class MembershipResponse(BaseModel):
    """Public representation of an organization membership."""

    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: MembershipRole
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
