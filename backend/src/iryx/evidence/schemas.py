"""IRYX Evidence and IngestionRun Pydantic Schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from iryx.evidence.models import IngestionStatus

__all__ = [
    "EvidenceRead",
    "IngestionRunRead",
]


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
