"""IRYX Investigation Cases Pydantic Schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from iryx.cases.models import CaseStatus

__all__ = [
    "CaseCreate",
    "CaseListResponse",
    "CaseOut",
    "CaseStatusUpdate",
]


class CaseCreate(BaseModel):
    """Schema for creating a new investigation case."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Intitulé concis du dossier d'investigation.",
    )
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="Contexte opérationnel ou description de l'incident.",
    )

    @field_validator("title")
    @classmethod
    def validate_title_non_empty(cls, value: str) -> str:
        """Ensure title contains at least one non-whitespace character and <= 255 chars."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Le titre du dossier ne peut pas être vide.")
        if len(cleaned) > 255:
            raise ValueError("Le titre du dossier ne peut pas dépasser 255 caractères.")
        return cleaned


class CaseStatusUpdate(BaseModel):
    """Schema for updating the operational lifecycle status of a case."""

    status: CaseStatus = Field(
        ...,
        description="Nouveau statut du cycle de vie ('open', 'in_progress', 'review', 'closed').",
    )


class CaseOut(BaseModel):
    """Public representation of an investigation case."""

    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    description: str | None = None
    status: CaseStatus
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaseListResponse(BaseModel):
    """Paginated collection of investigation cases."""

    items: list[CaseOut]
    total: int
    total_items: int = 0
    limit: int
    offset: int
    has_more: bool

    @model_validator(mode="before")
    @classmethod
    def populate_total_items(cls, data: Any) -> Any:
        """Ensure total_items is populated from total when missing."""
        if isinstance(data, dict) and "total_items" not in data and "total" in data:
            data["total_items"] = data["total"]
        elif hasattr(data, "total") and not getattr(data, "total_items", None):
            data.total_items = data.total
        return data
