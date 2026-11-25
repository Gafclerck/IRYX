"""Pydantic v2 schemas for InvestigationRun and Phase entities."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from iryx.orchestrator.models import InvestigationStatus, PhaseName, PhaseStatus


class PhaseOut(BaseModel):
    """Output schema for an investigation phase entity."""

    id: uuid.UUID
    investigation_run_id: uuid.UUID
    phase_name: PhaseName | str
    status: PhaseStatus
    started_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class InvestigationRunCreate(BaseModel):
    """Optional configuration payload when creating an investigation run."""

    notes: str | None = None


class InvestigationRunOut(BaseModel):
    """Output schema for an investigation run entity."""

    id: uuid.UUID
    case_id: uuid.UUID
    status: InvestigationStatus
    current_phase: PhaseName
    validated_plan: dict[str, Any] | None = None
    iteration_count: int = 0
    error_count: int = 0
    started_at: datetime
    updated_at: datetime
    phases: list[PhaseOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
