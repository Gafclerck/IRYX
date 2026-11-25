"""Procedural deterministic Executor Agent dispatching approved forensic tools (Story 5.5).

Conforms to FR17, D-08, D-09. Strictly zero LLM calls.
"""

import asyncio
import concurrent.futures
import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from iryx.core.exceptions import (
    EvidenceNotFoundInCaseException,
    PluginNotWhitelistedException,
    ToolExecutionFailedException,
    ToolExecutionTimeoutException,
    ToolNotFoundException,
    ValidationException,
)
from iryx.evidence.models import Evidence
from iryx.gateway.base import ToolExecutionContext
from iryx.gateway.registry import ToolRegistry, get_tool_registry
from iryx.gateway.runner import ToolRunner
from iryx.orchestrator.schemas import InvestigationPlan

logger = logging.getLogger("iryx.orchestrator.executor")


class ExecutorResult(BaseModel):
    """Result returned by ExecutorAgent execution."""

    status: str = "completed"  # "completed" | "paused" | "failed"
    tool_executions: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    error_count: int = 0
    executed_steps_count: int = 0
    total_steps_count: int = 0


class ExecutorAgent:
    """Procedural deterministic executor agent for investigation plans (FR17).

    Guarantees deterministic execution, strict evidence verification, and zero LLM calls.
    """

    def __init__(
        self,
        tool_runner: ToolRunner | None = None,
        tool_registry: ToolRegistry | None = None,
        db: Session | None = None,
    ) -> None:
        self.tool_registry = tool_registry or get_tool_registry()
        self.db = db
        self.tool_runner = tool_runner or ToolRunner(db=db, registry=self.tool_registry)

    async def execute(
        self,
        plan: InvestigationPlan | dict[str, Any] | None,
        case_id: uuid.UUID | str | None,
        run_id: uuid.UUID | str | None = None,
        db: Session | None = None,
    ) -> ExecutorResult:
        """Sequentially execute all steps in an approved investigation plan."""
        session_db = db or self.db

        # 1. Resolve and validate the investigation plan
        plan_obj: InvestigationPlan | None = None
        if plan is not None:
            if isinstance(plan, InvestigationPlan):
                plan_obj = plan
            elif isinstance(plan, dict):
                try:
                    plan_obj = InvestigationPlan.model_validate(plan)
                except Exception as exc:
                    logger.error("Failed to parse provided investigation plan: %s", exc)
                    return ExecutorResult(
                        status="failed",
                        errors=[f"Format de plan d'investigation invalide : {exc}"],
                        error_count=1,
                    )

        # Fallback to database validated_plan if plan is omitted
        has_run_context = (
            session_db is not None and case_id is not None and run_id is not None
        )
        if plan_obj is None and has_run_context:
            try:
                from iryx.orchestrator.models import InvestigationRun

                case_uuid = uuid.UUID(str(case_id))
                run_uuid = uuid.UUID(str(run_id))
                run = session_db.scalar(
                    select(InvestigationRun).where(
                        InvestigationRun.id == run_uuid,
                        InvestigationRun.case_id == case_uuid,
                    )
                )
                if run is not None and run.validated_plan is not None:
                    plan_obj = InvestigationPlan.model_validate(run.validated_plan)
            except Exception as exc:
                logger.warning("Could not load validated_plan from DB: %s", exc)

        if plan_obj is None or not plan_obj.steps:
            logger.error("No valid investigation plan found for execution")
            return ExecutorResult(
                status="failed",
                errors=["Aucun plan d'investigation validé disponible pour l'exécution."],
                error_count=1,
            )

        case_uuid_obj: uuid.UUID | None = None
        if case_id is not None:
            try:
                case_uuid_obj = uuid.UUID(str(case_id))
            except ValueError:
                case_uuid_obj = None

        run_uuid_obj: uuid.UUID | None = None
        if run_id is not None:
            try:
                run_uuid_obj = uuid.UUID(str(run_id))
            except ValueError:
                run_uuid_obj = None

        tool_executions: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        errors: list[str] = []
        error_count: int = 0
        executed_steps_count: int = 0
        is_paused: bool = False

        # Sort steps by step_id to ensure strict deterministic sequential order
        ordered_steps = sorted(plan_obj.steps, key=lambda s: s.step_id)

        for step in ordered_steps:
            step_blocking = getattr(step, "is_blocking", False) or step.parameters.get(
                "is_blocking", False
            )
            step_continue = getattr(step, "continue_on_error", True)
            if "continue_on_error" in step.parameters:
                step_continue = bool(step.parameters["continue_on_error"])
            elif step_blocking:
                step_continue = False

            # Verify tool in registry
            if not self.tool_registry.has(step.tool_name):
                err_msg = (
                    f"Étape {step.step_id} : L'outil '{step.tool_name}' n'est pas "
                    f"enregistré dans la Gateway."
                )
                logger.warning(err_msg)
                errors.append(err_msg)
                error_count += 1
                if step_blocking or not step_continue:
                    is_paused = True
                    break
                continue

            # Verify target evidence in DB if session is available
            if session_db is not None and case_uuid_obj is not None:
                evidence = session_db.scalar(
                    select(Evidence).where(
                        Evidence.id == step.target_evidence_id,
                        Evidence.case_id == case_uuid_obj,
                    )
                )
                if evidence is None:
                    err_msg = (
                        f"Étape {step.step_id} : La preuve ciblée '{step.target_evidence_id}' "
                        f"n'existe pas ou n'appartient pas au dossier {case_id}."
                    )
                    logger.warning(err_msg)
                    errors.append(err_msg)
                    error_count += 1
                    if step_blocking or not step_continue:
                        is_paused = True
                        break
                    continue

                if not evidence.sha256 or not evidence.sha256.strip():
                    err_msg = (
                        f"Étape {step.step_id} : La preuve ciblée '{step.target_evidence_id}' "
                        f"n'est pas scellée (SHA-256 manquant)."
                    )
                    logger.warning(err_msg)
                    errors.append(err_msg)
                    error_count += 1
                    if step_blocking or not step_continue:
                        is_paused = True
                        break
                    continue

            # Prepare parameters and execution context
            params = dict(step.parameters)
            if "evidence_id" not in params or params["evidence_id"] is None:
                params["evidence_id"] = str(step.target_evidence_id)

            ctx_case_id = case_uuid_obj or uuid.uuid4()
            context = ToolExecutionContext(
                case_id=ctx_case_id,
                agent_role="Executor",
                evidence_id=step.target_evidence_id,
                metadata={"step_id": step.step_id, "rationale": step.rationale},
            )

            try:
                result = await self.tool_runner.execute_tool(
                    tool_name=step.tool_name,
                    parameters=params,
                    context=context,
                )
                executed_steps_count += 1
                tool_executions.append(
                    {
                        "step_id": step.step_id,
                        "tool_name": step.tool_name,
                        "tool_execution_id": str(result.tool_execution_id)
                        if result.tool_execution_id
                        else None,
                        "status": str(result.status),
                        "result_sha256": result.result_sha256,
                        "duration_ms": result.duration_ms,
                    }
                )
                for obs in result.observations:
                    observations.append(obs)

            except (
                ToolExecutionTimeoutException,
                ToolNotFoundException,
                PluginNotWhitelistedException,
                ValidationException,
                EvidenceNotFoundInCaseException,
                ToolExecutionFailedException,
                Exception,
            ) as exc:
                err_msg = f"Étape {step.step_id} ({step.tool_name}) a échoué : {exc}"
                logger.error(err_msg)
                errors.append(err_msg)
                error_count += 1
                if step_blocking or not step_continue:
                    is_paused = True
                    break

        final_status = "paused" if is_paused else "completed"

        # Update database state if identifiers and db session are available
        if session_db is not None and case_uuid_obj is not None and run_uuid_obj is not None:
            try:
                from iryx.orchestrator.services import InvestigationService

                service = InvestigationService(session_db)
                if is_paused:
                    service.pause_at_executor(
                        case_id=case_uuid_obj,
                        run_id=run_uuid_obj,
                        error_count=error_count,
                    )
                else:
                    service.complete_executor_phase(
                        case_id=case_uuid_obj,
                        run_id=run_uuid_obj,
                        error_count=error_count,
                    )
            except Exception as exc:
                logger.warning("Could not persist executor phase transition in DB: %s", exc)

        return ExecutorResult(
            status=final_status,
            tool_executions=tool_executions,
            observations=observations,
            errors=errors,
            error_count=error_count,
            executed_steps_count=executed_steps_count,
            total_steps_count=len(ordered_steps),
        )

    def execute_sync(
        self,
        plan: InvestigationPlan | dict[str, Any] | None,
        case_id: uuid.UUID | str | None,
        run_id: uuid.UUID | str | None = None,
        db: Session | None = None,
    ) -> ExecutorResult:
        """Synchronously execute all plan steps, safely handling active event loops."""
        coro = self.execute(
            plan=plan,
            case_id=case_id,
            run_id=run_id,
            db=db,
        )
        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as thread_executor:
                future = thread_executor.submit(asyncio.run, coro)
                return future.result()
        except RuntimeError:
            return asyncio.run(coro)
