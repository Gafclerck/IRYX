"""Deterministic formal finding verifier without LLM calls (Story 6.3, FR23, NFR-REL-01).

Operates strictly via relational SQL set logic to validate that each UUID cited
in observation_refs and tool_execution_refs exists in the database and belongs
strictly to the current case_id (Invariant 1).
"""

import logging
import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from iryx.analytics.models import Finding, FindingStatus, Observation
from iryx.gateway.models import ToolExecution

logger = logging.getLogger("iryx.orchestrator.verifier")


class VerificationStatus(StrEnum):
    """Overall status of the deterministic verification process."""

    COMPLETED = "completed"
    FAILED = "failed"


class FindingVerificationDetail(BaseModel):
    """Detailed formal verification report for an individual finding."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    finding_id: uuid.UUID | str | None = None
    title: str
    is_valid: bool
    status: FindingStatus = FindingStatus.PROPOSED
    is_verified: bool = False
    valid_observation_refs: list[uuid.UUID] = Field(default_factory=list)
    missing_observation_refs: list[str] = Field(default_factory=list)
    foreign_observation_refs: list[uuid.UUID] = Field(default_factory=list)
    valid_tool_execution_refs: list[uuid.UUID] = Field(default_factory=list)
    missing_tool_execution_refs: list[str] = Field(default_factory=list)
    foreign_tool_execution_refs: list[uuid.UUID] = Field(default_factory=list)
    rejection_reason: str | None = None
    errors: list[str] = Field(default_factory=list)


class VerificationResult(BaseModel):
    """Aggregated outcome of the deterministic verification phase."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    status: VerificationStatus | str = VerificationStatus.COMPLETED
    total_findings: int = 0
    verified_count: int = 0
    rejected_count: int = 0
    details: list[FindingVerificationDetail] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class FindingVerifier:
    """Deterministic formal verifier without LLM calls (FR23, NFR-REL-01)."""

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def _verify_internal(
        self,
        findings: list[Any] | None = None,
        case_id: uuid.UUID | str | None = None,
        db: Session | None = None,
    ) -> VerificationResult:
        """Internal synchronous deterministic verification executing SQL queries."""
        session = db or self.db

        # Parse case_uuid if provided
        case_uuid: uuid.UUID | None = None
        if case_id is not None:
            try:
                case_uuid = uuid.UUID(str(case_id))
            except (ValueError, TypeError, AttributeError):
                case_uuid = None

        # Determine findings to verify
        raw_findings: list[Any] = []
        if findings is not None:
            raw_findings = list(findings)
        elif case_uuid is not None and session is not None:
            try:
                stmt = (
                    select(Finding)
                    .where(Finding.case_id == case_uuid, Finding.status == FindingStatus.PROPOSED)
                    .order_by(Finding.created_at.asc(), Finding.id.asc())
                )
                raw_findings = list(session.scalars(stmt).all())
            except Exception as exc:
                logger.warning(
                    "Could not query proposed findings from DB for case %s: %s",
                    case_uuid,
                    exc,
                )

        # Scenario 54: No findings to verify
        if not raw_findings:
            logger.info("FindingVerifier: No findings to verify for case %s.", case_uuid)
            return VerificationResult(
                status=VerificationStatus.COMPLETED,
                total_findings=0,
                verified_count=0,
                rejected_count=0,
                details=[],
                findings=[],
                errors=[],
            )

        # Scenario 55: Findings to verify but no DB session
        if session is None:
            err_msg = (
                "Une session de base de données (SQLAlchemy Session) est obligatoire "
                "pour la certification formelle déterministe des constats."
            )
            logger.error(err_msg)
            return VerificationResult(
                status=VerificationStatus.FAILED,
                total_findings=len(raw_findings),
                verified_count=0,
                rejected_count=0,
                details=[],
                findings=[],
                errors=[err_msg],
            )

        # If case_uuid is still None, try extracting from findings
        if case_uuid is None:
            for f in raw_findings:
                f_case = (
                    getattr(f, "case_id", None) if not isinstance(f, dict) else f.get("case_id")
                )
                if f_case:
                    try:
                        case_uuid = uuid.UUID(str(f_case))
                        break
                    except Exception:
                        pass

        if case_uuid is None:
            err_msg = "L'identifiant de dossier (case_id) est requis pour vérifier les constats."
            logger.error(err_msg)
            return VerificationResult(
                status=VerificationStatus.FAILED,
                total_findings=len(raw_findings),
                verified_count=0,
                rejected_count=0,
                details=[],
                findings=[],
                errors=[err_msg],
            )

        # Parse finding payloads and collect all UUID candidates for batch querying
        parsed_findings_data: list[dict[str, Any]] = []
        all_obs_uuids: set[uuid.UUID] = set()
        all_tool_uuids: set[uuid.UUID] = set()

        for f in raw_findings:
            if isinstance(f, dict):
                f_id = f.get("id")
                f_title = str(f.get("title") or "Sans titre")
                raw_obs_refs = f.get("observation_refs") or []
                raw_tool_refs = f.get("tool_execution_refs") or []
                f_dict = dict(f)
            else:
                f_id = getattr(f, "id", None)
                f_title = str(getattr(f, "title", "Sans titre"))
                raw_obs_refs = getattr(f, "observation_refs", []) or []
                raw_tool_refs = getattr(f, "tool_execution_refs", []) or []
                if hasattr(f, "model_dump"):
                    f_dict = f.model_dump(mode="json")
                else:
                    f_dict = {
                        "id": str(f.id) if getattr(f, "id", None) else None,
                        "case_id": (
                            str(f.case_id) if getattr(f, "case_id", None) else str(case_uuid)
                        ),
                        "title": f.title,
                        "severity": str(getattr(f, "severity", "low")),
                        "confidence": str(getattr(f, "confidence", "medium")),
                        "finding_type": str(getattr(f, "finding_type", "fact")),
                        "status": str(getattr(f, "status", "proposed")),
                        "observation_refs": [str(x) for x in raw_obs_refs],
                        "tool_execution_refs": [str(x) for x in raw_tool_refs],
                    }

            # Parse observation UUIDs
            valid_parsed_obs: list[uuid.UUID] = []
            malformed_obs: list[str] = []
            for r in raw_obs_refs:
                if isinstance(r, uuid.UUID):
                    valid_parsed_obs.append(r)
                else:
                    try:
                        valid_parsed_obs.append(uuid.UUID(str(r)))
                    except (ValueError, TypeError, AttributeError):
                        malformed_obs.append(str(r))

            # Parse tool execution UUIDs
            valid_parsed_tools: list[uuid.UUID] = []
            malformed_tools: list[str] = []
            for r in raw_tool_refs:
                if isinstance(r, uuid.UUID):
                    valid_parsed_tools.append(r)
                else:
                    try:
                        valid_parsed_tools.append(uuid.UUID(str(r)))
                    except (ValueError, TypeError, AttributeError):
                        malformed_tools.append(str(r))

            all_obs_uuids.update(valid_parsed_obs)
            all_tool_uuids.update(valid_parsed_tools)

            parsed_findings_data.append(
                {
                    "raw_finding": f,
                    "dict_finding": f_dict,
                    "id": f_id,
                    "title": f_title,
                    "parsed_obs": valid_parsed_obs,
                    "malformed_obs": malformed_obs,
                    "parsed_tools": valid_parsed_tools,
                    "malformed_tools": malformed_tools,
                    "had_obs_refs": bool(raw_obs_refs),
                    "had_tool_refs": bool(raw_tool_refs),
                }
            )

        # Batch query for observations (Design Note 2 & 3)
        obs_case_map: dict[uuid.UUID, uuid.UUID] = {}
        if all_obs_uuids:
            stmt_obs = select(Observation.id, Observation.case_id).where(
                Observation.id.in_(all_obs_uuids)
            )
            for row in session.execute(stmt_obs).all():
                obs_case_map[row[0]] = row[1]

        # Batch query for tool executions (Design Note 2 & 3)
        tool_case_map: dict[uuid.UUID, uuid.UUID] = {}
        if all_tool_uuids:
            stmt_tools = select(ToolExecution.id, ToolExecution.case_id).where(
                ToolExecution.id.in_(all_tool_uuids)
            )
            for row in session.execute(stmt_tools).all():
                tool_case_map[row[0]] = row[1]

        # Perform formal verification for each finding
        details: list[FindingVerificationDetail] = []
        updated_findings_dicts: list[dict[str, Any]] = []
        errors_list: list[str] = []
        db_has_updates = False

        for item in parsed_findings_data:
            f_id = item["id"]
            f_title = item["title"]
            f_dict = item["dict_finding"]

            valid_obs: list[uuid.UUID] = []
            missing_obs: list[str] = list(item["malformed_obs"])
            foreign_obs: list[uuid.UUID] = []

            for obs_uuid in item["parsed_obs"]:
                if obs_uuid in obs_case_map:
                    if obs_case_map[obs_uuid] == case_uuid:
                        valid_obs.append(obs_uuid)
                    else:
                        foreign_obs.append(obs_uuid)
                else:
                    missing_obs.append(str(obs_uuid))

            valid_tools: list[uuid.UUID] = []
            missing_tools: list[str] = list(item["malformed_tools"])
            foreign_tools: list[uuid.UUID] = []

            for tool_uuid in item["parsed_tools"]:
                if tool_uuid in tool_case_map:
                    if tool_case_map[tool_uuid] == case_uuid:
                        valid_tools.append(tool_uuid)
                    else:
                        foreign_tools.append(tool_uuid)
                else:
                    missing_tools.append(str(tool_uuid))

            # Invariant check:
            # 1. At least 1 valid observation ref
            # 2. At least 1 valid tool execution ref
            # 3. 0 missing observation refs
            # 4. 0 foreign observation refs
            # 5. 0 missing tool execution refs
            # 6. 0 foreign tool execution refs
            is_valid = (
                len(valid_obs) > 0
                and len(valid_tools) > 0
                and len(missing_obs) == 0
                and len(foreign_obs) == 0
                and len(missing_tools) == 0
                and len(foreign_tools) == 0
            )

            finding_errors: list[str] = []
            if not item["had_obs_refs"]:
                finding_errors.append(
                    "Le constat ne comporte aucune référence d'observation (ancrage requis)."
                )
            elif len(valid_obs) == 0:
                finding_errors.append("Aucune référence d'observation valide n'a pu être vérifiée.")

            if not item["had_tool_refs"]:
                finding_errors.append(
                    "Le constat ne comporte aucune référence d'exécution d'outil (ancrage requis)."
                )
            elif len(valid_tools) == 0:
                finding_errors.append(
                    "Aucune référence d'exécution d'outil valide n'a pu être vérifiée."
                )

            if missing_obs:
                finding_errors.append(
                    f"Références d'observation inexistantes ou malformées : {missing_obs}"
                )
            if foreign_obs:
                finding_errors.append(
                    f"Références d'observation appartenant à un autre dossier : {foreign_obs}"
                )
            if missing_tools:
                finding_errors.append(
                    f"Références d'outils inexistantes ou malformées : {missing_tools}"
                )
            if foreign_tools:
                finding_errors.append(
                    f"Références d'outils appartenant à un autre dossier : {foreign_tools}"
                )

            if is_valid:
                detail = FindingVerificationDetail(
                    finding_id=f_id,
                    title=f_title,
                    is_valid=True,
                    status=FindingStatus.PROPOSED,
                    is_verified=True,
                    valid_observation_refs=valid_obs,
                    missing_observation_refs=[],
                    foreign_observation_refs=[],
                    valid_tool_execution_refs=valid_tools,
                    missing_tool_execution_refs=[],
                    foreign_tool_execution_refs=[],
                    rejection_reason=None,
                    errors=[],
                )
                f_dict["status"] = "proposed"
                f_dict["is_verified"] = True
                f_dict["rejection_reason"] = None
            else:
                rejection_reason = "HALLUCINATED_REFERENCE_DETECTED"
                detail = FindingVerificationDetail(
                    finding_id=f_id,
                    title=f_title,
                    is_valid=False,
                    status=FindingStatus.REJECTED,
                    is_verified=False,
                    valid_observation_refs=valid_obs,
                    missing_observation_refs=missing_obs,
                    foreign_observation_refs=foreign_obs,
                    valid_tool_execution_refs=valid_tools,
                    missing_tool_execution_refs=missing_tools,
                    foreign_tool_execution_refs=foreign_tools,
                    rejection_reason=rejection_reason,
                    errors=finding_errors,
                )
                f_dict["status"] = "rejected"
                f_dict["is_verified"] = False
                f_dict["rejection_reason"] = rejection_reason

                # Log security warning
                logger.warning(
                    "HALLUCINATED_REFERENCE_DETECTED: Constat '%s' (ID: %s, Case: %s) rejeté. "
                    "Raisons : %s",
                    f_title,
                    f_id,
                    case_uuid,
                    "; ".join(finding_errors),
                )
                err_desc = "; ".join(finding_errors)
                errors_list.append(
                    f"HALLUCINATED_REFERENCE_DETECTED pour le constat '{f_title}' : {err_desc}"
                )

                # Persist rejection in DB if finding exists
                raw_obj = item["raw_finding"]
                if isinstance(raw_obj, Finding):
                    raw_obj.status = FindingStatus.REJECTED
                    db_has_updates = True
                elif f_id is not None:
                    try:
                        f_uuid = uuid.UUID(str(f_id))
                        db_finding = session.scalar(
                            select(Finding).where(
                                Finding.id == f_uuid, Finding.case_id == case_uuid
                            )
                        )
                        if db_finding is not None:
                            db_finding.status = FindingStatus.REJECTED
                            db_has_updates = True
                    except Exception as exc:
                        logger.warning(
                            "Could not persist rejected status for finding %s: %s",
                            f_id,
                            exc,
                        )

            details.append(detail)
            updated_findings_dicts.append(f_dict)

        if db_has_updates:
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                logger.error("Failed to commit rejected finding statuses to DB: %s", exc)

        verified_count = sum(1 for d in details if d.is_valid)
        rejected_count = sum(1 for d in details if not d.is_valid)

        logger.info(
            "FindingVerifier completed for case %s: %d total, %d verified, %d rejected",
            case_uuid,
            len(details),
            verified_count,
            rejected_count,
        )

        return VerificationResult(
            status=VerificationStatus.COMPLETED,
            total_findings=len(details),
            verified_count=verified_count,
            rejected_count=rejected_count,
            details=details,
            findings=updated_findings_dicts,
            errors=errors_list,
        )

    async def verify(
        self,
        findings: list[Any] | None = None,
        case_id: uuid.UUID | str | None = None,
        db: Session | None = None,
    ) -> VerificationResult:
        """Asynchronously execute formal verification without LLM calls (NFR-REL-01)."""
        return self._verify_internal(findings=findings, case_id=case_id, db=db)

    def verify_sync(
        self,
        findings: list[Any] | None = None,
        case_id: uuid.UUID | str | None = None,
        db: Session | None = None,
    ) -> VerificationResult:
        """Synchronously execute formal verification without LLM calls (NFR-REL-01)."""
        return self._verify_internal(findings=findings, case_id=case_id, db=db)
