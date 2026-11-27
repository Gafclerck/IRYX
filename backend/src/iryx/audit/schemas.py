"""Pydantic schemas for the audit trail (Story 8.5)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator
from pydantic.config import ConfigDict


class AuditEventOut(BaseModel):
    """Serialized audit trail event; secret-free by construction."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_id: uuid.UUID | None
    actor_id: uuid.UUID | None
    action: str
    target_type: str
    target_id: uuid.UUID
    payload_hash: str
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AuditEventListResponse(BaseModel):
    """Paginated audit trail envelope (mirrors reporting ReportListResponse)."""

    items: list[AuditEventOut]
    total: int = Field(..., ge=0)
    total_items: int = Field(default=0, ge=0)
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)
    has_more: bool

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_total_items(cls, data: Any) -> Any:
        """Ensure total_items mirrors total when the caller omits it."""
        if isinstance(data, dict) and data.get("total_items") is None and "total" in data:
            updated = dict(data)
            updated["total_items"] = updated["total"]
            return updated
        return data
