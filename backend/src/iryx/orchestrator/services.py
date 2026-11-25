"""Investigation Run business logic and anti-concurrency orchestration services."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from iryx.cases.models import Case, CaseStatus
from iryx.core.exceptions import (
    CannotResumeTerminatedSessionException,
    CaseNotFoundException,
    InvalidGateStateException,
    InvalidPlanException,
    InvestigationAlreadyRunningException,
    InvestigationNotFoundException,
    PlanNotFoundException,
    UnreviewedFindingsException,
    ValidationException,
)
from iryx.orchestrator.checkpointer import get_checkpointer
from iryx.orchestrator.graph import _sanitize_context, build_investigation_graph
from iryx.orchestrator.models import (
    InvestigationRun,
    InvestigationStatus,
    Phase,
    PhaseName,
    PhaseStatus,
)
from iryx.orchestrator.schemas import (
    AnonymizedPreviewOut,
    H1Decision,
    H1DecisionRequest,
    H1DecisionResponse,
    H2Decision,
    H2DecisionRequest,
    H2DecisionResponse,
    H3Decision,
    H3DecisionRequest,
    H3DecisionResponse,
    InvestigationPlan,
    PhaseOut,
)

logger = logging.getLogger("iryx.orchestrator")


class InvestigationService:
    """Service handling investigation run lifecycles, concurrency checks, and phase transitions."""

    def __init__(self, db: Session, checkpointer: Any | None = None) -> None:
        self.db = db
        self.checkpointer = checkpointer or get_checkpointer()

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

    def get_investigation_plan(self, case_id: uuid.UUID, run_id: uuid.UUID) -> InvestigationPlan:
        """Retrieve the validated investigation plan associated with a run.

        Raises:
            InvestigationNotFoundException: If the run doesn't exist or doesn't belong to the case.
            PlanNotFoundException: If no plan has been generated or associated with the run yet.
            InvalidPlanException: If the stored plan data fails schema validation.
        """
        run = self.get_investigation_run(case_id=case_id, run_id=run_id)
        if run.validated_plan is None:
            raise PlanNotFoundException(
                message="Aucun plan d'investigation n'est associé à cette session.",
                code="PLAN_NOT_FOUND",
            )
        try:
            return InvestigationPlan.model_validate(run.validated_plan)
        except ValidationError as exc:
            raise InvalidPlanException(
                message=f"Plan d'investigation invalide en base : {exc}",
            ) from exc

    def pause_at_gate_h1(self, case_id: uuid.UUID, run_id: uuid.UUID) -> InvestigationRun:
        """Pause an investigation run at Human Gate H1 awaiting analyst validation.

        Sets run.status to paused and current_phase to waiting_h1, closing the previous
        active phase and ensuring a gate_h1 phase is active.
        """
        run = self.get_investigation_run(case_id=case_id, run_id=run_id)

        if run.status in (InvestigationStatus.COMPLETED, InvestigationStatus.FAILED):
            raise ValidationException(
                message=f"Impossible de suspendre une session avec le statut '{run.status}'.",
                code="INVALID_STATUS_TRANSITION",
            )

        now = datetime.now(UTC)
        run.status = InvestigationStatus.PAUSED
        run.current_phase = PhaseName.WAITING_H1
        run.updated_at = now

        # Close currently active phase if not already gate_h1
        active_phase = self.db.scalar(
            select(Phase).where(
                Phase.investigation_run_id == run.id,
                Phase.status == PhaseStatus.ACTIVE,
            )
        )
        if active_phase is not None and active_phase.phase_name != PhaseName.GATE_H1:
            active_phase.status = PhaseStatus.COMPLETED
            active_phase.completed_at = now
            gate_phase = Phase(
                id=uuid.uuid4(),
                investigation_run_id=run.id,
                phase_name=PhaseName.GATE_H1,
                status=PhaseStatus.ACTIVE,
                started_at=now,
            )
            self.db.add(gate_phase)
        elif active_phase is None:
            gate_phase = Phase(
                id=uuid.uuid4(),
                investigation_run_id=run.id,
                phase_name=PhaseName.GATE_H1,
                status=PhaseStatus.ACTIVE,
                started_at=now,
            )
            self.db.add(gate_phase)

        self.db.commit()
        self.db.refresh(run)

        logger.info(
            "Investigation run paused at Human Gate H1",
            extra={
                "context": {
                    "case_id": str(case_id),
                    "run_id": str(run_id),
                    "current_phase": str(run.current_phase),
                    "status": str(run.status),
                }
            },
        )
        return run

    def arbitrate_gate_h1(
        self,
        case_id: uuid.UUID,
        run_id: uuid.UUID,
        decision_request: H1DecisionRequest,
        user_id: uuid.UUID | None = None,
    ) -> H1DecisionResponse:
        """Arbitrate Human Gate H1: approve, modify, or reject the proposed investigation plan."""
        # Pessimistic row-level lock on InvestigationRun
        run = self.db.scalar(
            select(InvestigationRun)
            .options(selectinload(InvestigationRun.phases))
            .where(
                InvestigationRun.id == run_id,
                InvestigationRun.case_id == case_id,
            )
            .with_for_update()
        )
        if run is None:
            raise InvestigationNotFoundException(
                message=(
                    "La session d'investigation demandée n'existe pas ou "
                    "n'appartient pas à ce dossier."
                )
            )

        # Invariant check: run must be paused at gate H1
        is_gate_h1 = run.status == InvestigationStatus.PAUSED and str(run.current_phase) in (
            PhaseName.GATE_H1,
            PhaseName.WAITING_H1,
            "gate_h1",
            "waiting_h1",
        )
        if not is_gate_h1:
            raise InvalidGateStateException(
                message=(
                    "La session d'investigation n'est pas en attente d'arbitrage sur la porte H1."
                ),
                code="INVALID_GATE_STATE",
            )

        now = datetime.now(UTC)
        run.updated_at = now

        # Close current active gate phase
        active_phase = self.db.scalar(
            select(Phase).where(
                Phase.investigation_run_id == run.id,
                Phase.status == PhaseStatus.ACTIVE,
            )
        )
        if active_phase is not None:
            active_phase.status = PhaseStatus.COMPLETED
            active_phase.completed_at = now

        message: str

        if decision_request.decision == H1Decision.APPROVE:
            if run.validated_plan is None:
                raise PlanNotFoundException(
                    message=(
                        "Aucun plan d'investigation n'est associé à cette session pour approbation."
                    ),
                    code="PLAN_NOT_FOUND",
                )
            run.status = InvestigationStatus.RUNNING
            run.current_phase = PhaseName.EXECUTOR

            # Next phase: executor
            next_phase = Phase(
                id=uuid.uuid4(),
                investigation_run_id=run.id,
                phase_name=PhaseName.EXECUTOR,
                status=PhaseStatus.ACTIVE,
                started_at=now,
            )
            self.db.add(next_phase)
            message = (
                "Plan d'investigation approuvé avec succès. Transition vers la phase d'exécution."
            )

        elif decision_request.decision == H1Decision.MODIFY:
            if decision_request.modified_plan is None:
                raise ValidationException(
                    message="Un plan modifié est requis pour la décision 'modify'.",
                    code="MISSING_MODIFIED_PLAN",
                )

            # Validate against InvestigationPlan
            try:
                if isinstance(decision_request.modified_plan, InvestigationPlan):
                    plan_obj = decision_request.modified_plan
                elif isinstance(decision_request.modified_plan, dict):
                    plan_obj = InvestigationPlan.model_validate(decision_request.modified_plan)
                else:
                    raise ValueError("Format de plan invalide.")
            except Exception as exc:
                raise InvalidPlanException(
                    message=f"Plan d'investigation modifié invalide : {exc}",
                    code="INVALID_PLAN",
                ) from exc

            # Verify tools in ToolRegistry whitelist
            from iryx.gateway.registry import get_tool_registry

            tool_reg = get_tool_registry()
            authorized_tools = set(tool_reg.list_tool_names()) | set(
                getattr(tool_reg, "_whitelist", set())
            )
            for step in plan_obj.steps:
                if step.tool_name not in authorized_tools:
                    raise InvalidPlanException(
                        message=(
                            f"Outil non autorisé ou inconnu '{step.tool_name}'. "
                            f"Outils autorisés : {sorted(authorized_tools)}"
                        ),
                        code="INVALID_PLAN",
                    )

            # Verify target evidences belong to this case
            from iryx.evidence.models import Evidence

            target_evidence_ids = {step.target_evidence_id for step in plan_obj.steps}
            existing_ids = set(
                self.db.scalars(
                    select(Evidence.id).where(
                        Evidence.case_id == case_id,
                        Evidence.id.in_(target_evidence_ids),
                        Evidence.sha256.isnot(None),
                        Evidence.sha256 != "",
                    )
                ).all()
            )
            for target_id in target_evidence_ids:
                if target_id not in existing_ids:
                    raise InvalidPlanException(
                        message=(
                            f"La preuve ciblée '{target_id}' n'existe pas, "
                            "n'appartient pas à ce dossier ou n'est pas scellée."
                        ),
                        code="INVALID_PLAN",
                    )

            plan_dict = plan_obj.model_dump(mode="json")
            run.validated_plan = plan_dict
            run.status = InvestigationStatus.RUNNING
            run.current_phase = PhaseName.EXECUTOR

            # Next phase: executor
            next_phase = Phase(
                id=uuid.uuid4(),
                investigation_run_id=run.id,
                phase_name=PhaseName.EXECUTOR,
                status=PhaseStatus.ACTIVE,
                started_at=now,
            )
            self.db.add(next_phase)
            message = (
                "Plan d'investigation modifié et validé avec succès. "
                "Transition vers la phase d'exécution."
            )

        elif decision_request.decision == H1Decision.REJECT:
            if decision_request.return_to_planner:
                if run.iteration_count >= 5:
                    raise ValidationException(
                        message="Nombre maximal d'itérations de replanification atteint (5).",
                        code="MAX_ITERATIONS_REACHED",
                    )
                run.status = InvestigationStatus.RUNNING
                run.current_phase = PhaseName.PLANNER
                run.iteration_count += 1
                run.validated_plan = None

                # Next phase: planner
                next_phase = Phase(
                    id=uuid.uuid4(),
                    investigation_run_id=run.id,
                    phase_name=PhaseName.PLANNER,
                    status=PhaseStatus.ACTIVE,
                    started_at=now,
                )
                self.db.add(next_phase)
                message = (
                    "Plan d'investigation rejeté avec demande de replanification. "
                    "Retour vers la phase Planner."
                )
            else:
                run.status = InvestigationStatus.COMPLETED
                run.current_phase = PhaseName.GATE_H1
                message = (
                    "Plan d'investigation rejeté par l'analyste. Session d'investigation terminée."
                )
        else:
            raise ValidationException(
                message=f"Décision d'arbitrage invalide : '{decision_request.decision}'.",
                code="INVALID_DECISION",
            )

        self.db.commit()
        self.db.refresh(run)

        logger.info(
            "Human Gate H1 arbitration recorded",
            extra={
                "context": {
                    "case_id": str(case_id),
                    "run_id": str(run.id),
                    "user_id": str(user_id) if user_id else None,
                    "decision": str(decision_request.decision),
                    "feedback": decision_request.feedback,
                    "return_to_planner": decision_request.return_to_planner,
                    "current_phase": str(run.current_phase),
                    "status": str(run.status),
                }
            },
        )

        return H1DecisionResponse(
            run_id=run.id,
            case_id=run.case_id,
            status=run.status,
            current_phase=run.current_phase,
            decision=decision_request.decision,
            validated_plan=run.validated_plan,
            message=message,
            phases=[PhaseOut.model_validate(p) for p in run.phases],
        )

    def pause_at_gate_h2(self, case_id: uuid.UUID, run_id: uuid.UUID) -> InvestigationRun:
        """Pause an investigation run at Human Gate H2 awaiting analyst validation of findings.

        Sets run.status to paused and current_phase to waiting_h2, closing the previous
        active phase and ensuring a gate_h2 phase is active.
        """
        run = self.get_investigation_run(case_id=case_id, run_id=run_id)

        if run.status in (InvestigationStatus.COMPLETED, InvestigationStatus.FAILED):
            raise ValidationException(
                message=f"Impossible de suspendre une session avec le statut '{run.status}'.",
                code="INVALID_STATUS_TRANSITION",
            )

        now = datetime.now(UTC)
        run.status = InvestigationStatus.PAUSED
        run.current_phase = PhaseName.WAITING_H2
        run.updated_at = now

        # Close currently active phase if not already gate_h2
        active_phase = self.db.scalar(
            select(Phase).where(
                Phase.investigation_run_id == run.id,
                Phase.status == PhaseStatus.ACTIVE,
            )
        )
        if active_phase is not None and active_phase.phase_name != PhaseName.GATE_H2:
            active_phase.status = PhaseStatus.COMPLETED
            active_phase.completed_at = now
            gate_phase = Phase(
                id=uuid.uuid4(),
                investigation_run_id=run.id,
                phase_name=PhaseName.GATE_H2,
                status=PhaseStatus.ACTIVE,
                started_at=now,
            )
            self.db.add(gate_phase)
        elif active_phase is None:
            gate_phase = Phase(
                id=uuid.uuid4(),
                investigation_run_id=run.id,
                phase_name=PhaseName.GATE_H2,
                status=PhaseStatus.ACTIVE,
                started_at=now,
            )
            self.db.add(gate_phase)

        self.db.commit()
        self.db.refresh(run)

        logger.info(
            "Investigation run paused at Human Gate H2",
            extra={
                "context": {
                    "case_id": str(case_id),
                    "run_id": str(run_id),
                    "current_phase": str(run.current_phase),
                    "status": str(run.status),
                }
            },
        )
        return run

    def arbitrate_gate_h2(
        self,
        case_id: uuid.UUID,
        run_id: uuid.UUID,
        decision_request: H2DecisionRequest,
        user_id: uuid.UUID | None = None,
    ) -> H2DecisionResponse:
        """Arbitrate Human Gate H2: proceed to gate_h3 or reject after validating findings."""
        # Pessimistic row-level lock on InvestigationRun
        run = self.db.scalar(
            select(InvestigationRun)
            .options(selectinload(InvestigationRun.phases))
            .where(
                InvestigationRun.id == run_id,
                InvestigationRun.case_id == case_id,
            )
            .with_for_update()
        )
        if run is None:
            raise InvestigationNotFoundException(
                message=(
                    "La session d'investigation demandée n'existe pas ou "
                    "n'appartient pas à ce dossier."
                )
            )

        # Invariant check: run must be paused at gate H2
        is_gate_h2 = run.status == InvestigationStatus.PAUSED and str(run.current_phase) in (
            PhaseName.GATE_H2,
            PhaseName.WAITING_H2,
            "gate_h2",
            "waiting_h2",
        )
        if not is_gate_h2:
            raise InvalidGateStateException(
                message=(
                    "La session d'investigation n'est pas en attente d'arbitrage sur la porte H2."
                ),
                code="INVALID_GATE_STATE",
                status_code=400,
            )

        now = datetime.now(UTC)
        run.updated_at = now

        message: str

        if decision_request.decision == H2Decision.PROCEED:
            from iryx.analytics.models import Finding, FindingStatus

            proposed_count = (
                self.db.scalar(
                    select(func.count(Finding.id)).where(
                        Finding.case_id == case_id,
                        Finding.status == FindingStatus.PROPOSED,
                    )
                )
                or 0
            )
            if proposed_count > 0:
                raise UnreviewedFindingsException(
                    message=(
                        f"Impossible de valider la porte H2 : {proposed_count} constat(s) "
                        "sont encore en attente de revue ('proposed')."
                    ),
                )

            # Close current active gate phase
            active_phase = self.db.scalar(
                select(Phase).where(
                    Phase.investigation_run_id == run.id,
                    Phase.status == PhaseStatus.ACTIVE,
                )
            )
            if active_phase is not None:
                active_phase.status = PhaseStatus.COMPLETED
                active_phase.completed_at = now

            run.status = InvestigationStatus.RUNNING
            run.current_phase = PhaseName.GATE_H3

            next_phase = Phase(
                id=uuid.uuid4(),
                investigation_run_id=run.id,
                phase_name=PhaseName.GATE_H3,
                status=PhaseStatus.ACTIVE,
                started_at=now,
            )
            self.db.add(next_phase)
            message = (
                "Validation des constats approuvée à la porte H2. "
                "Transition vers la phase suivante."
            )

        elif decision_request.decision == H2Decision.REJECT:
            # Close current active gate phase
            active_phase = self.db.scalar(
                select(Phase).where(
                    Phase.investigation_run_id == run.id,
                    Phase.status == PhaseStatus.ACTIVE,
                )
            )
            if active_phase is not None:
                active_phase.status = PhaseStatus.COMPLETED
                active_phase.completed_at = now

            run.status = InvestigationStatus.COMPLETED
            run.current_phase = PhaseName.GATE_H2
            message = (
                "Session d'investigation rejetée à la porte H2 par l'analyste. Session terminée."
            )
        else:
            raise ValidationException(
                message=f"Décision d'arbitrage invalide : '{decision_request.decision}'.",
                code="INVALID_DECISION",
                status_code=400,
            )

        self.db.commit()
        self.db.refresh(run)

        logger.info(
            "Human Gate H2 arbitration recorded",
            extra={
                "context": {
                    "case_id": str(case_id),
                    "run_id": str(run.id),
                    "user_id": str(user_id) if user_id else None,
                    "decision": str(decision_request.decision),
                    "feedback": decision_request.feedback,
                    "current_phase": str(run.current_phase),
                    "status": str(run.status),
                }
            },
        )

        return H2DecisionResponse(
            run_id=run.id,
            case_id=run.case_id,
            status=run.status,
            current_phase=run.current_phase,
            decision=decision_request.decision,
            message=message,
            phases=[PhaseOut.model_validate(p) for p in run.phases],
        )

    def pause_at_gate_h3(self, case_id: uuid.UUID, run_id: uuid.UUID) -> InvestigationRun:
        """Pause an investigation run at Human Gate H3 awaiting analyst authorization.

        Sets run.status to paused and current_phase to waiting_h3, closing the previous
        active phase and ensuring a gate_h3 phase is active.
        """
        run = self.get_investigation_run(case_id=case_id, run_id=run_id)

        if run.status in (InvestigationStatus.COMPLETED, InvestigationStatus.FAILED):
            raise ValidationException(
                message=f"Impossible de suspendre une session avec le statut '{run.status}'.",
                code="INVALID_STATUS_TRANSITION",
            )

        now = datetime.now(UTC)
        run.status = InvestigationStatus.PAUSED
        run.current_phase = PhaseName.WAITING_H3
        run.updated_at = now

        # Close currently active phase if not already gate_h3
        active_phase = self.db.scalar(
            select(Phase).where(
                Phase.investigation_run_id == run.id,
                Phase.status == PhaseStatus.ACTIVE,
            )
        )
        if active_phase is not None and active_phase.phase_name != PhaseName.GATE_H3:
            active_phase.status = PhaseStatus.COMPLETED
            active_phase.completed_at = now
            gate_phase = Phase(
                id=uuid.uuid4(),
                investigation_run_id=run.id,
                phase_name=PhaseName.GATE_H3,
                status=PhaseStatus.ACTIVE,
                started_at=now,
            )
            self.db.add(gate_phase)
        elif active_phase is None:
            gate_phase = Phase(
                id=uuid.uuid4(),
                investigation_run_id=run.id,
                phase_name=PhaseName.GATE_H3,
                status=PhaseStatus.ACTIVE,
                started_at=now,
            )
            self.db.add(gate_phase)

        self.db.commit()
        self.db.refresh(run)

        logger.info(
            "Investigation run paused at Human Gate H3",
            extra={
                "context": {
                    "case_id": str(case_id),
                    "run_id": str(run_id),
                    "current_phase": str(run.current_phase),
                    "status": str(run.status),
                }
            },
        )
        return run

    def arbitrate_gate_h3(
        self,
        case_id: uuid.UUID,
        run_id: uuid.UUID,
        decision_request: H3DecisionRequest,
        user_id: uuid.UUID | None = None,
    ) -> H3DecisionResponse:
        """Arbitrate Human Gate H3: approve the external LLM send or use the local template."""
        # Pessimistic row-level lock on InvestigationRun
        run = self.db.scalar(
            select(InvestigationRun)
            .options(selectinload(InvestigationRun.phases))
            .where(
                InvestigationRun.id == run_id,
                InvestigationRun.case_id == case_id,
            )
            .with_for_update()
        )
        if run is None:
            raise InvestigationNotFoundException(
                message=(
                    "La session d'investigation demandée n'existe pas ou "
                    "n'appartient pas à ce dossier."
                )
            )

        # Invariant check: run must be paused at gate H3
        is_gate_h3 = run.status == InvestigationStatus.PAUSED and str(run.current_phase) in (
            PhaseName.GATE_H3,
            PhaseName.WAITING_H3,
            "gate_h3",
            "waiting_h3",
        )
        if not is_gate_h3:
            raise InvalidGateStateException(
                message=(
                    "La session d'investigation n'est pas en attente d'arbitrage sur la porte H3."
                ),
                code="INVALID_GATE_STATE",
                status_code=400,
            )

        # The checkpointer is the source of truth for gate decisions (Story 5.6).
        # Persist the H3 verdict there BEFORE advancing the DB run so that a
        # resume cannot silently re-approve an external LLM send after a reject.
        approved = decision_request.decision == H3Decision.APPROVE
        graph = build_investigation_graph(checkpointer=self.checkpointer)
        config = {"configurable": {"thread_id": str(run.id)}}
        snapshot = graph.get_state(config)
        context = dict((snapshot.values or {}).get("context") or {})
        context["h3_feedback"] = decision_request.feedback
        if not approved:
            context["local_report_mode"] = True

        state_update: dict[str, Any] = {
            "h3_approved": approved,
            "h3_rejected": not approved,
            "current_phase": "gate_h3" if approved else "reporting",
            "status": "running",
            "context": _sanitize_context(context),
        }
        try:
            graph.update_state(config, state_update)
        except Exception as exc:
            raise ValidationException(
                message="Impossible d'enregistrer la décision H3 dans le checkpointer.",
                code="H3_DECISION_PERSISTENCE_FAILED",
            ) from exc

        now = datetime.now(UTC)
        run.updated_at = now

        # Close current active gate phase
        active_phase = self.db.scalar(
            select(Phase).where(
                Phase.investigation_run_id == run.id,
                Phase.status == PhaseStatus.ACTIVE,
            )
        )
        if active_phase is not None:
            active_phase.status = PhaseStatus.COMPLETED
            active_phase.completed_at = now

        if decision_request.decision == H3Decision.APPROVE:
            run.status = InvestigationStatus.RUNNING
            run.current_phase = PhaseName.REPORTING

            next_phase = Phase(
                id=uuid.uuid4(),
                investigation_run_id=run.id,
                phase_name=PhaseName.REPORTING,
                status=PhaseStatus.ACTIVE,
                started_at=now,
            )
            self.db.add(next_phase)
            message = (
                "Autorisation d'envoi vers le LLM externe accordée à la porte H3. "
                "Transition vers le nœud de rédaction du rapport."
            )
        else:
            # REJECT: fall back to the deterministic local template (Story 8.2, AC 2)
            run.status = InvestigationStatus.RUNNING
            run.current_phase = PhaseName.REPORTING

            next_phase = Phase(
                id=uuid.uuid4(),
                investigation_run_id=run.id,
                phase_name=PhaseName.REPORTING,
                status=PhaseStatus.ACTIVE,
                started_at=now,
            )
            self.db.add(next_phase)
            message = (
                "Envoi externe refusé à la porte H3 par l'analyste. "
                "Le rapport sera compilé par le gabarit déterministe local, sans appel LLM."
            )

        self.db.commit()
        self.db.refresh(run)

        logger.info(
            "Human Gate H3 arbitration recorded",
            extra={
                "context": {
                    "case_id": str(case_id),
                    "run_id": str(run.id),
                    "user_id": str(user_id) if user_id else None,
                    "decision": str(decision_request.decision),
                    "feedback": decision_request.feedback,
                    "current_phase": str(run.current_phase),
                    "status": str(run.status),
                }
            },
        )

        return H3DecisionResponse(
            run_id=run.id,
            case_id=run.case_id,
            status=run.status,
            current_phase=run.current_phase,
            decision=decision_request.decision,
            message=message,
            phases=[PhaseOut.model_validate(p) for p in run.phases],
        )

    def get_anonymized_preview(self, case_id: uuid.UUID, run_id: uuid.UUID) -> AnonymizedPreviewOut:
        """Retourne un aperçu pseudonymisé de la synthèse du dossier avant la porte H3 (FR20)."""
        from iryx.analytics.models import Finding, FindingStatus
        from iryx.reporting.pseudonymizer import DeterministicPseudonymizer

        run = self.get_investigation_run(case_id=case_id, run_id=run_id)

        findings = self.db.scalars(
            select(Finding)
            .where(
                Finding.case_id == case_id,
                Finding.status != FindingStatus.REJECTED,
            )
            .order_by(Finding.created_at)
        ).all()

        sections = [
            f"[{finding.severity}] {finding.title}\n"
            f"Type : {finding.finding_type}\nStatut : {finding.status}"
            for finding in findings
        ]
        text = (
            "\n\n".join(sections)
            if sections
            else "Aucune conclusion disponible pour ce dossier."
        )

        result = DeterministicPseudonymizer().pseudonymize(text, case_id=str(case_id))

        return AnonymizedPreviewOut(
            run_id=run.id,
            case_id=run.case_id,
            anonymized_text=result.pseudonymized_text,
            entity_count=result.entity_count,
            has_entities=result.has_entities,
        )

    def complete_executor_phase(
        self,
        case_id: uuid.UUID,
        run_id: uuid.UUID,
        error_count: int = 0,
    ) -> InvestigationRun:
        """Mark executor phase completed, increment error count, and transition to analyst."""
        run = self.db.scalar(
            select(InvestigationRun)
            .where(
                InvestigationRun.id == run_id,
                InvestigationRun.case_id == case_id,
            )
            .with_for_update()
        )
        if run is None:
            raise InvestigationNotFoundException(
                message=(
                    "La session d'investigation demandée n'existe pas ou "
                    "n'appartient pas à ce dossier."
                )
            )

        now = datetime.now(UTC)
        run.error_count += max(error_count, 0)
        run.current_phase = PhaseName.ANALYST
        run.status = InvestigationStatus.RUNNING
        run.updated_at = now

        # Close active executor phase if present
        active_phase = self.db.scalar(
            select(Phase)
            .where(
                Phase.investigation_run_id == run.id,
                Phase.phase_name.in_([PhaseName.EXECUTOR, PhaseName.EXECUTION]),
                Phase.status == PhaseStatus.ACTIVE,
            )
            .order_by(Phase.started_at.desc())
        )
        if active_phase is not None:
            active_phase.status = PhaseStatus.COMPLETED
            active_phase.completed_at = now

        # Open next phase: analyst
        next_phase = Phase(
            id=uuid.uuid4(),
            investigation_run_id=run.id,
            phase_name=PhaseName.ANALYST,
            status=PhaseStatus.ACTIVE,
            started_at=now,
        )
        self.db.add(next_phase)
        self.db.commit()
        self.db.refresh(run)

        logger.info(
            "Executor phase completed; transitioned to analyst",
            extra={
                "context": {
                    "case_id": str(case_id),
                    "run_id": str(run_id),
                    "error_count": run.error_count,
                    "current_phase": str(run.current_phase),
                }
            },
        )
        return run

    def pause_at_executor(
        self,
        case_id: uuid.UUID,
        run_id: uuid.UUID,
        error_count: int = 0,
    ) -> InvestigationRun:
        """Suspend investigation run during executor phase due to a blocking error."""
        run = self.db.scalar(
            select(InvestigationRun)
            .where(
                InvestigationRun.id == run_id,
                InvestigationRun.case_id == case_id,
            )
            .with_for_update()
        )
        if run is None:
            raise InvestigationNotFoundException(
                message=(
                    "La session d'investigation demandée n'existe pas ou "
                    "n'appartient pas à ce dossier."
                )
            )

        now = datetime.now(UTC)
        run.error_count += max(error_count, 0)
        run.status = InvestigationStatus.PAUSED
        run.current_phase = PhaseName.EXECUTOR
        run.updated_at = now
        self.db.commit()
        self.db.refresh(run)

        logger.warning(
            "Investigation run paused at executor due to blocking error",
            extra={
                "context": {
                    "case_id": str(case_id),
                    "run_id": str(run_id),
                    "error_count": run.error_count,
                    "status": str(run.status),
                }
            },
        )
        return run

    def resume_investigation(
        self,
        case_id: uuid.UUID,
        run_id: uuid.UUID,
    ) -> InvestigationRun:
        """Resume an interrupted or paused investigation session from its checkpoint.

        Acquires a row-level lock on InvestigationRun to prevent race conditions.
        Rejects resumption of sessions with terminal status ('completed' or 'failed')
        with CannotResumeTerminatedSessionException (HTTP 400).
        Restores state from checkpointer and continues LangGraph state graph execution.
        """
        run = self.db.scalar(
            select(InvestigationRun)
            .where(
                InvestigationRun.id == run_id,
                InvestigationRun.case_id == case_id,
            )
            .with_for_update()
        )
        if run is None:
            raise InvestigationNotFoundException(
                message=(
                    "La session d'investigation demandée n'existe pas ou "
                    "n'appartient pas à ce dossier."
                )
            )

        if run.status in (InvestigationStatus.COMPLETED, InvestigationStatus.FAILED):
            msg = (
                f"Impossible de reprendre une session d'investigation terminée ou échouée "
                f"(statut : '{run.status}')."
            )
            raise CannotResumeTerminatedSessionException(
                message=msg,
                code="CANNOT_RESUME_TERMINATED_SESSION",
            )

        # Build graph with configured checkpointer
        graph = build_investigation_graph(checkpointer=self.checkpointer)
        config = {"configurable": {"thread_id": str(run.id)}}

        # Retrieve state snapshot from checkpointer
        state_snapshot = graph.get_state(config)

        # Inject transient runtime context into graph
        from iryx.gateway.registry import get_tool_registry
        from iryx.gateway.runner import ToolRunner
        from iryx.orchestrator.graph import set_runtime_context

        set_runtime_context(
            {
                "db": self.db,
                "tool_registry": get_tool_registry(),
                "tool_runner": ToolRunner(db=self.db),
            }
        )

        try:
            if state_snapshot and state_snapshot.values:
                state_update: dict[str, Any] = {}

                if run.current_phase in (PhaseName.EXECUTOR, PhaseName.EXECUTION):
                    state_update["h1_approved"] = True
                    state_update["current_phase"] = "executor"
                    state_update["status"] = "running"
                    if run.validated_plan is not None:
                        state_update["plan"] = run.validated_plan
                elif run.current_phase in (
                    PhaseName.GATE_H3,
                    PhaseName.WAITING_H3,
                    "gate_h3",
                    "waiting_h3",
                ):
                    state_update["h1_approved"] = True
                    state_update["h2_approved"] = True
                    state_update["current_phase"] = "gate_h3"
                    state_update["status"] = "running"
                    if run.validated_plan is not None:
                        state_update["plan"] = run.validated_plan
                elif run.current_phase in (PhaseName.REPORTING, "reporting"):
                    snapshot_values = state_snapshot.values or {}
                    snapshot_context = snapshot_values.get("context") or {}
                    h3_decided = bool(snapshot_values.get("h3_approved")) or bool(
                        snapshot_values.get("h3_rejected")
                    ) or bool(snapshot_context.get("local_report_mode"))
                    state_update["h1_approved"] = True
                    state_update["h2_approved"] = True
                    # Sans verdict H3 enregistré, on repasse par la porte au lieu
                    # de réapprouver implicitement un envoi vers un LLM externe.
                    state_update["current_phase"] = "reporting" if h3_decided else "gate_h3"
                    state_update["status"] = "running"
                    if run.validated_plan is not None:
                        state_update["plan"] = run.validated_plan

                result = graph.invoke(state_update, config=config)
            else:
                run_status_str = (
                    "running" if run.status == InvestigationStatus.RUNNING else str(run.status)
                )
                initial_state: dict[str, Any] = {
                    "case_id": str(run.case_id),
                    "run_id": str(run.id),
                    "status": run_status_str,
                    "current_phase": str(run.current_phase),
                    "iteration_count": run.iteration_count,
                    "error_count": run.error_count,
                    "plan": run.validated_plan,
                }
                if run.current_phase in (PhaseName.EXECUTOR, PhaseName.EXECUTION):
                    initial_state["h1_approved"] = True
                elif run.current_phase in (
                    PhaseName.GATE_H3,
                    PhaseName.WAITING_H3,
                    "gate_h3",
                    "waiting_h3",
                    PhaseName.REPORTING,
                    "reporting",
                ):
                    initial_state["h1_approved"] = True
                    initial_state["h2_approved"] = True
                    initial_state["plan"] = run.validated_plan
                    # Aucun verdict H3 dans le checkpointer : le graphe doit
                    # s'arrêter à la porte et attendre l'arbitrage humain.

                result = graph.invoke(initial_state, config=config)
        finally:
            set_runtime_context({})

        now = datetime.now(UTC)
        new_phase_str = result.get("current_phase", run.current_phase)
        new_status_str = result.get("status", "running")

        run.current_phase = new_phase_str
        if new_status_str in ("running", "paused", "completed", "failed", "pending"):
            run.status = InvestigationStatus(new_status_str)
        run.error_count = result.get("error_count", run.error_count)
        run.updated_at = now

        if result.get("plan") is not None and run.validated_plan is None:
            run.validated_plan = result["plan"]

        # Synchronize Phase history in DB
        active_phase = self.db.scalar(
            select(Phase)
            .where(
                Phase.investigation_run_id == run.id,
                Phase.status == PhaseStatus.ACTIVE,
            )
            .order_by(Phase.started_at.desc())
        )
        if active_phase is not None and active_phase.phase_name != new_phase_str:
            active_phase.status = PhaseStatus.COMPLETED
            active_phase.completed_at = now
            next_phase = Phase(
                id=uuid.uuid4(),
                investigation_run_id=run.id,
                phase_name=new_phase_str,
                status=PhaseStatus.ACTIVE,
                started_at=now,
            )
            self.db.add(next_phase)

        self.db.commit()
        self.db.refresh(run)

        logger.info(
            "Investigation run resumed successfully",
            extra={
                "context": {
                    "case_id": str(case_id),
                    "run_id": str(run.id),
                    "current_phase": str(run.current_phase),
                    "status": str(run.status),
                }
            },
        )
        return self.get_investigation_run(case_id=case_id, run_id=run.id)
