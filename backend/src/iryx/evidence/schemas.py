"""IRYX Evidence and IngestionRun Pydantic Schemas."""

import contextlib
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from iryx.evidence.models import IngestionStatus

__all__ = [
    "EvidenceIngestionStatusResponse",
    "EvidenceListResponse",
    "EvidenceRead",
    "EvidenceUploadResponse",
    "IngestionRunRead",
]


class EvidenceUploadResponse(BaseModel):
    """Response payload returned when evidence is successfully accepted for ingestion."""

    evidence_id: uuid.UUID
    ingestion_run_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


class IngestionRunRead(BaseModel):
    """Public representation of an evidence ingestion run."""

    id: uuid.UUID
    evidence_id: uuid.UUID
    status: IngestionStatus
    progress: int = Field(..., ge=0, le=100)
    error_message: str | None = None
    started_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class EvidenceRead(BaseModel):
    """Public representation of an evidence entity."""

    id: uuid.UUID
    case_id: uuid.UUID
    original_name: str = Field(..., min_length=1)
    file_size: int = Field(..., ge=0)
    sha256: str | None = None
    detected_type: str | None = None
    imported_by: uuid.UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvidenceIngestionStatusResponse(BaseModel):
    """Status payload for polling evidence ingestion progress and sealed metadata."""

    status: IngestionStatus
    progress: int = Field(..., ge=0, le=100)
    error_message: str | None = None
    sha256: str | None = None
    detected_type: str | None = None

    model_config = ConfigDict(from_attributes=True)


class EvidenceListResponse(BaseModel):
    """Paginated collection of evidence files for an investigation case."""

    items: list[EvidenceRead]
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
        if isinstance(data, dict) and data.get("total_items") is None and "total" in data:
            data["total_items"] = data["total"]
        elif hasattr(data, "total") and getattr(data, "total_items", None) is None:
            with contextlib.suppress(AttributeError, TypeError):
                data.total_items = data.total
        return data
