"""Pydantic v2 schemas for InvestigationRun, Phase, and InvestigationPlan entities."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from iryx.orchestrator.models import InvestigationStatus, PhaseName, PhaseStatus


class InvestigationPlanStep(BaseModel):
    """Single forensic step in an investigation plan."""

    step_id: int = Field(..., gt=0, description="Order of execution index for the step.")
    tool_name: str = Field(..., description="Name of the forensic tool to execute.")
    target_evidence_id: uuid.UUID = Field(
        ..., description="Identifier of the target evidence artifact."
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters passed to the forensic tool execution.",
    )
    rationale: str = Field(
        ..., description="Forensic justification explaining why this step is necessary."
    )

    model_config = ConfigDict(from_attributes=True)


class InvestigationPlan(BaseModel):
    """Bounded forensic investigation plan proposed by PlannerAgent (FR17, NFR-PERF-05)."""

    steps: list[InvestigationPlanStep] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Ordered list of investigation steps (maximum 10 steps).",
    )
    summary: str = Field(
        default="",
        description="Overview or rationale of the overall investigation plan.",
    )

    @field_validator("steps")
    @classmethod
    def validate_steps_limit(cls, v: list[InvestigationPlanStep]) -> list[InvestigationPlanStep]:
        if len(v) < 1:
            raise ValueError("Le plan d'investigation doit comporter au moins 1 étape.")
        if len(v) > 10:
            raise ValueError("Le plan d'investigation ne peut comporter plus de 10 étapes.")
        return v

    model_config = ConfigDict(from_attributes=True)


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
