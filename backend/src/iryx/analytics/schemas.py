"""IRYX Analytics and Finding Pydantic Schemas."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from iryx.analytics.models import (
    FindingConfidence,
    FindingSeverity,
    FindingStatus,
    FindingType,
)

__all__ = [
    "FindingBase",
    "FindingConfidence",
    "FindingCreate",
    "FindingListResponse",
    "FindingOut",
    "FindingReview",
    "FindingSeverity",
    "FindingStatus",
    "FindingType",
    "FindingUpdate",
]


class FindingBase(BaseModel):
    """Base schema for investigation findings."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Intitulé concis du constat d'investigation.",
    )
    severity: FindingSeverity = Field(
        ...,
        description="Niveau de sévérité ('low', 'medium', 'high', 'critical').",
    )
    confidence: FindingConfidence = Field(
        default=FindingConfidence.MEDIUM,
        description="Niveau de confiance ('low', 'medium', 'high').",
    )
    finding_type: FindingType = Field(
        default=FindingType.FACT,
        description="Classification ('fact', 'inference', 'hypothesis').",
    )
    observation_refs: list[uuid.UUID] = Field(
        default_factory=list,
        description="Identifiants d'observations justificatives réelles.",
    )
    tool_execution_refs: list[uuid.UUID] = Field(
        default_factory=list,
        description="Identifiants d'exécutions d'outils associées.",
    )

    @field_validator("title")
    @classmethod
    def validate_title_non_empty(cls, value: str) -> str:
        """Ensure title contains non-whitespace characters and is within bounds."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Le titre du constat ne peut pas être vide.")
        if len(cleaned) > 255:
            raise ValueError("Le titre du constat ne peut pas dépasser 255 caractères.")
        return cleaned


class FindingCreate(FindingBase):
    """Schema for proposing or registering a new finding."""

    pass


class FindingUpdate(BaseModel):
    """Schema for updating an existing technical finding."""

    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Nouvel intitulé concis du constat.",
    )
    severity: FindingSeverity | None = Field(
        default=None,
        description="Nouveau niveau de sévérité.",
    )
    confidence: FindingConfidence | None = Field(
        default=None,
        description="Nouveau niveau de confiance.",
    )
    finding_type: FindingType | None = Field(
        default=None,
        description="Nouveau type de constat.",
    )
    status: FindingStatus | None = Field(
        default=None,
        description="Nouveau statut opérationnel ('proposed', 'validated', 'rejected').",
    )
    observation_refs: list[uuid.UUID] | None = Field(
        default=None,
        description="Nouvelle liste d'identifiants d'observations.",
    )
    tool_execution_refs: list[uuid.UUID] | None = Field(
        default=None,
        description="Nouvelle liste d'identifiants d'exécutions d'outils.",
    )

    @field_validator("title")
    @classmethod
    def validate_title_optional(cls, value: str | None) -> str | None:
        """Ensure updated title is non-empty if supplied."""
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Le titre du constat ne peut pas être vide.")
        if len(cleaned) > 255:
            raise ValueError("Le titre du constat ne peut pas dépasser 255 caractères.")
        return cleaned


class FindingReview(BaseModel):
    """Schema for analyst human-in-the-loop review at Gate H2."""

    action: Literal["validate", "reject"] = Field(
        ...,
        description="Décision de revue humaine : 'validate' ou 'reject'.",
    )
    severity: FindingSeverity | None = Field(
        default=None,
        description="Ajustement optionnel du niveau de sévérité.",
    )
    confidence: FindingConfidence | None = Field(
        default=None,
        description="Ajustement optionnel du niveau de confiance.",
    )


class FindingOut(FindingBase):
    """Public representation of an investigation finding."""

    id: uuid.UUID
    case_id: uuid.UUID
    status: FindingStatus
    created_by: uuid.UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FindingListResponse(BaseModel):
    """Paginated collection of investigation findings."""

    items: list[FindingOut]
    total: int = Field(..., ge=0)
    total_items: int = Field(default=0, ge=0)
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)
    has_more: bool

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_total_items(cls, data: Any) -> Any:
        """Ensure total_items is populated from total when missing."""
        if isinstance(data, dict) and "total_items" not in data and "total" in data:
            data["total_items"] = data["total"]
        elif (
            hasattr(data, "__dict__")
            and hasattr(data, "total")
            and not getattr(data, "total_items", None)
        ):
            data.total_items = data.total
        return data
