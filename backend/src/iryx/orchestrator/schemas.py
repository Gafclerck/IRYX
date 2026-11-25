"""Pydantic v2 schemas for InvestigationRun, Phase, and InvestigationPlan entities."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from iryx.orchestrator.models import InvestigationStatus, PhaseName, PhaseStatus


class H1Decision(StrEnum):
    """Arbitration decisions for Human Gate H1."""

    APPROVE = "approve"
    MODIFY = "modify"
    REJECT = "reject"


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
    is_blocking: bool = Field(
        default=False,
        description=(
            "Indique si l'échec technique de cette étape doit suspendre immédiatement l'exécution."
        ),
    )
    continue_on_error: bool = Field(
        default=True,
        description=("Indique si l'Executor doit poursuivre les étapes suivantes en cas d'erreur."),
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
        step_ids = [step.step_id for step in v]
        expected_ids = list(range(1, len(v) + 1))
        if step_ids != expected_ids:
            raise ValueError(
                f"Les step_id doivent être strictement uniques et séquentiels de 1 à {len(v)}. "
                f"Reçu : {step_ids}"
            )
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
    current_phase: PhaseName | str
    validated_plan: dict[str, Any] | None = None
    iteration_count: int = 0
    error_count: int = 0
    started_at: datetime
    updated_at: datetime
    phases: list[PhaseOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class H1DecisionRequest(BaseModel):
    """Payload submitted by analyst to arbitrate Human Gate H1."""

    decision: H1Decision = Field(
        ...,
        description="Arbitration decision: 'approve', 'modify', or 'reject'.",
    )
    modified_plan: dict[str, Any] | InvestigationPlan | None = Field(
        default=None,
        description="Modified investigation plan (mandatory if decision is 'modify').",
    )
    feedback: str | None = Field(
        default=None,
        max_length=2000,
        description="Analyst feedback or observations.",
    )
    return_to_planner: bool = Field(
        default=False,
        description="If True on rejection, loops back to PlannerAgent instead of halting.",
    )

    model_config = ConfigDict(from_attributes=True)


class H1DecisionResponse(BaseModel):
    """Response returned after Human Gate H1 arbitration."""

    run_id: uuid.UUID
    case_id: uuid.UUID
    status: InvestigationStatus
    current_phase: PhaseName | str
    decision: H1Decision
    validated_plan: dict[str, Any] | None = None
    message: str
    phases: list[PhaseOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class H2Decision(StrEnum):
    """Arbitration decisions for Human Gate H2."""

    PROCEED = "proceed"
    REJECT = "reject"


class H2DecisionRequest(BaseModel):
    """Payload submitted by analyst to arbitrate Human Gate H2."""

    decision: H2Decision = Field(
        ...,
        description="Arbitration decision: 'proceed' or 'reject'.",
    )
    feedback: str | None = Field(
        default=None,
        max_length=2000,
        description="Analyst feedback or observations.",
    )

    model_config = ConfigDict(from_attributes=True)


class H2DecisionResponse(BaseModel):
    """Response returned after Human Gate H2 arbitration."""

    run_id: uuid.UUID
    case_id: uuid.UUID
    status: InvestigationStatus
    current_phase: PhaseName | str
    decision: H2Decision
    message: str
    phases: list[PhaseOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class H3Decision(StrEnum):
    """Arbitration decisions for Human Gate H3."""

    APPROVE = "approve"
    REJECT = "reject"


class H3DecisionRequest(BaseModel):
    """Payload submitted by analyst to arbitrate Human Gate H3."""

    decision: H3Decision = Field(
        ...,
        description="Arbitration decision: 'approve' or 'reject' (mode hors-ligne).",
    )
    feedback: str | None = Field(
        default=None,
        max_length=2000,
        description="Analyst feedback or observations.",
    )

    model_config = ConfigDict(from_attributes=True)


class H3DecisionResponse(BaseModel):
    """Response returned after Human Gate H3 arbitration."""

    run_id: uuid.UUID
    case_id: uuid.UUID
    status: InvestigationStatus
    current_phase: PhaseName | str
    decision: H3Decision
    message: str
    phases: list[PhaseOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AnonymizedPreviewOut(BaseModel):
    """Aperçu anonymisé de la synthèse soumise à l'envoi externe (porte H3, FR20)."""

    run_id: uuid.UUID
    case_id: uuid.UUID
    anonymized_text: str = Field(..., description="Texte pseudonymisé proposé à l'envoi.")
    entity_count: int = Field(
        default=0, description="Nombre d'entités démasquées puis pseudonymisées."
    )
    has_entities: bool = Field(
        default=False, description="Indique si au moins une entité a été anonymisée."
    )
