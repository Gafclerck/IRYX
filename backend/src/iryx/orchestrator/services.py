"""Investigation Run business logic and anti-concurrency orchestration services."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from iryx.cases.models import Case, CaseStatus
from iryx.core.exceptions import (
    CaseNotFoundException,
    InvalidPlanException,
    InvestigationAlreadyRunningException,
    InvestigationNotFoundException,
    ValidationException,
)
from iryx.orchestrator.models import (
    InvestigationRun,
    InvestigationStatus,
    Phase,
    PhaseName,
    PhaseStatus,
)
from iryx.orchestrator.schemas import InvestigationPlan

logger = logging.getLogger("iryx.orchestrator")


class InvestigationService:
    """Service handling investigation run lifecycles, concurrency checks, and phase transitions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def start_investigation(self, case_id: uuid.UUID) -> InvestigationRun:
        """Create a new investigation run and initial triage phase for a case.

        Acquires a row-level lock on the Case to prevent TOCTOU race conditions.
        Rejects creation if the case is closed or if an active session ('pending',
        'running', 'paused') already exists.
        """
        # Row lock on Case (EC-1 / BH-1)
        case = self.db.scalar(select(Case).where(Case.id == case_id).with_for_update())
        if case is None:
            raise CaseNotFoundException()

        # Invariant check: cannot start investigation on a closed case (BH-14)
        if case.status == CaseStatus.CLOSED:
            raise ValidationException(
                message="Impossible de démarrer une investigation sur un dossier fermé.",
                code="CASE_CLOSED",
            )

        active_run = self.db.scalar(
            select(InvestigationRun).where(
                InvestigationRun.case_id == case_id,
                InvestigationRun.status.in_(
                    [
                        InvestigationStatus.PENDING,
                        InvestigationStatus.RUNNING,
                        InvestigationStatus.PAUSED,
                    ]
                ),
            )
        )
        if active_run is not None:
            raise InvestigationAlreadyRunningException(
                message="Une session d'investigation est déjà active sur ce dossier."
            )

        now = datetime.now(UTC)
        run = InvestigationRun(
            id=uuid.uuid4(),
            case_id=case_id,
            status=InvestigationStatus.RUNNING,
            current_phase=PhaseName.TRIAGE,
            iteration_count=0,
            error_count=0,
            started_at=now,
            updated_at=now,
        )
        self.db.add(run)
        self.db.flush()

        initial_phase = Phase(
            id=uuid.uuid4(),
            investigation_run_id=run.id,
            phase_name=PhaseName.TRIAGE,
            status=PhaseStatus.ACTIVE,
            started_at=now,
        )
        self.db.add(initial_phase)
        self.db.commit()

        logger.info(
            "Investigation run started successfully",
            extra={
                "context": {
                    "case_id": str(case_id),
                    "run_id": str(run.id),
                    "current_phase": str(run.current_phase),
                }
            },
        )

        return self.get_investigation_run(case_id=case_id, run_id=run.id)

    def get_investigation_run(self, case_id: uuid.UUID, run_id: uuid.UUID) -> InvestigationRun:
        """Retrieve an investigation run by id for a given case."""
        logger.info(
            "Retrieving investigation run",
            extra={"context": {"case_id": str(case_id), "run_id": str(run_id)}},
        )
        run = self.db.scalar(
            select(InvestigationRun)
            .options(selectinload(InvestigationRun.phases))
            .where(
                InvestigationRun.id == run_id,
                InvestigationRun.case_id == case_id,
            )
        )
        if run is None:
            raise InvestigationNotFoundException(
                message=(
                    "La session d'investigation demandée n'existe pas ou "
                    "n'appartient pas à ce dossier."
                )
            )
        return run

    def list_investigation_runs(self, case_id: uuid.UUID) -> list[InvestigationRun]:
        """List all investigation runs for a case ordered by started_at descending."""
        logger.info(
            "Listing investigation runs",
            extra={"context": {"case_id": str(case_id)}},
        )
        stmt = (
            select(InvestigationRun)
            .options(selectinload(InvestigationRun.phases))
            .where(InvestigationRun.case_id == case_id)
            .order_by(InvestigationRun.started_at.desc(), InvestigationRun.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def save_validated_plan(
        self,
        case_id: uuid.UUID,
        run_id: uuid.UUID,
        plan: InvestigationPlan | dict[str, Any],
    ) -> InvestigationRun:
        """Persist the validated investigation plan onto the InvestigationRun entity."""
        run = self.get_investigation_run(case_id=case_id, run_id=run_id)

        plan_data: dict[str, Any]
        if isinstance(plan, InvestigationPlan):
            plan_data = plan.model_dump(mode="json")
        elif isinstance(plan, dict):
            try:
                validated = InvestigationPlan.model_validate(plan)
                plan_data = validated.model_dump(mode="json")
            except ValidationError as exc:
                raise InvalidPlanException(
                    message=f"Plan d'investigation invalide : {exc}",
                ) from exc
        else:
            raise InvalidPlanException(
                message="Format de plan d'investigation invalide pour la persistance.",
            )

        run.validated_plan = plan_data
        run.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(run)

        logger.info(
            "Investigation plan successfully saved to run",
            extra={
                "context": {
                    "case_id": str(case_id),
                    "run_id": str(run_id),
                    "steps_count": len(plan_data.get("steps", [])),
                }
            },
        )
        return run

    def pause_investigation(
        self,
        case_id: uuid.UUID,
        run_id: uuid.UUID,
        reason: str | None = None,
    ) -> InvestigationRun:
        """Pause an investigation run (e.g. waiting for sealed evidence)."""
        run = self.get_investigation_run(case_id=case_id, run_id=run_id)

        if run.status in (InvestigationStatus.COMPLETED, InvestigationStatus.FAILED):
            raise ValidationException(
                message=f"Impossible de suspendre une session avec le statut '{run.status}'.",
                code="INVALID_STATUS_TRANSITION",
            )

        run.status = InvestigationStatus.PAUSED
        run.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(run)

        logger.info(
            "Investigation run paused",
            extra={
                "context": {
                    "case_id": str(case_id),
                    "run_id": str(run_id),
                    "reason": reason or "attente de preuves scellées",
                }
            },
        )
        return run
