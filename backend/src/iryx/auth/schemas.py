"""IRYX Authentication and User Pydantic Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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
