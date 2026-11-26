"""Report generation, versioning and access-control services (Story 8.3)."""

import contextlib
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from iryx.analytics.models import Finding, FindingStatus, Observation
from iryx.analytics.services import TimelineService
from iryx.auth.models import Membership
from iryx.cases.models import Case
from iryx.core.exceptions import (
    CaseNotFoundException,
    InsufficientPermissionsException,
    ReportGenerationFailedException,
    ValidationException,
)
from iryx.evidence.models import Evidence
from iryx.reporting.compiler import compile_report, sha256_text
from iryx.reporting.models import Report
from iryx.reporting.rapporteur_agent import RapporteurAgent
from iryx.reporting.schemas import ReportContent, ReportFormat, ReportOut, ReportStatus
from iryx.reporting.verdicts import verdict_flag

logger = logging.getLogger("iryx.reporting.services")

_MAX_VERSION_RETRIES = 3


def _safe_uuid(value: Any, label: str = "identifiant") -> uuid.UUID:
    """Parse a UUID strictly and raise a typed validation error otherwise."""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationException(
            message=f"{label} invalide.",
            code="INVALID_UUID",
            status_code=422,
        ) from exc


def _is_version_conflict(exc: IntegrityError) -> bool:
    """Return True only for the ``(case_id, version, format)`` uniqueness violation."""
    orig = exc.orig
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    if constraint:
        return constraint == "uq_reports_case_version_format"
    if orig is None:
        return False
    message = str(orig).lower()
    return (
        "uq_reports_case_version_format" in message
        or "unique constraint failed: reports.case_id, reports.version, reports.format" in message
    )


class ReportService:
    """Centralize all Story 8.3 invariants for report persistence."""

    def __init__(
        self,
        db: Session,
        agent: RapporteurAgent | None = None,
        case_service: Any | None = None,
    ) -> None:
        self.db = db
        self.agent = agent or RapporteurAgent()
        self.case_service = case_service

    def _authorize(
        self,
        case_id: uuid.UUID,
        user_id: uuid.UUID | None,
        *,
        internal: bool,
        lock: bool = False,
    ) -> Case | None:
        """Check membership before reading the case body."""
        if internal:
            stmt = select(Case)
            if lock:
                stmt = stmt.with_for_update()
            return self.db.scalar(stmt.where(Case.id == case_id))

        if user_id is None:
            raise InsufficientPermissionsException(
                message="Un utilisateur authentifié est requis pour accéder aux rapports."
            )

        authorized_id = self.db.scalar(
            select(Case.id)
            .join(Membership, Membership.organization_id == Case.organization_id)
            .where(Case.id == case_id, Membership.user_id == user_id)
            .limit(1)
        )
        if authorized_id is None:
            raise InsufficientPermissionsException(
                message="Accès refusé à ce dossier d'investigation."
            )

        stmt = select(Case).where(Case.id == case_id)
        if lock:
            stmt = stmt.with_for_update()
        case = self.db.scalar(stmt)
        if case is None:
            raise InsufficientPermissionsException(
                message="Accès refusé à ce dossier d'investigation."
            )
        return case

    def _load_context(
        self,
        case: Case,
        case_id: uuid.UUID,
        run_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        """Collect case-scoped evidence, observations, timeline and validated findings."""
        evidences = list(
            self.db.scalars(
                select(Evidence)
                .where(Evidence.case_id == case_id)
                .order_by(Evidence.created_at, Evidence.id)
            ).all()
        )
        observations = list(
            self.db.scalars(
                select(Observation)
                .where(Observation.case_id == case_id)
                .order_by(Observation.timestamp_utc.asc().nulls_last(), Observation.id)
            ).all()
        )
        timeline_response = TimelineService(self.db).get_timeline_projection(case_id=case_id)
        timeline_events = [
            event.model_dump(mode="json") for event in timeline_response.events
        ] + [event.model_dump(mode="json") for event in timeline_response.undated_events]

        validated_findings = list(
            self.db.scalars(
                select(Finding)
                .where(
                    Finding.case_id == case_id,
                    Finding.status == FindingStatus.VALIDATED,
                )
                .order_by(Finding.created_at, Finding.id)
            ).all()
        )
        invalid_findings = list(
            self.db.scalars(
                select(Finding)
                .where(
                    Finding.case_id == case_id,
                    Finding.status != FindingStatus.VALIDATED,
                )
                .order_by(Finding.created_at, Finding.id)
            ).all()
        )

        return {
            "case": self._serialize(case),
            "case_id": case_id,
            "run_id": run_id,
            "incident_description": case.description or "",
            "evidences": [self._serialize(item) for item in evidences],
            "observations": [self._serialize(item) for item in observations],
            "timeline": timeline_events,
            "facts": [self._serialize(item) for item in validated_findings],
            "invalid_finding_titles": [
                str(finding.title) for finding in invalid_findings if finding.title
            ],
        }

    @staticmethod
    def _serialize(value: Any) -> dict[str, Any]:
        """Serialize an ORM row without leaking SQLAlchemy internals."""
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            return dict(model_dump(mode="json"))
        return {
            column.name: getattr(value, column.name)
            for column in value.__table__.columns
        }

    @staticmethod
    def _external_mode(
        h3_approved: bool | None,
        h3_rejected: Any,
        local_report_mode: Any,
    ) -> bool:
        """Mirror the agent's strict external-mode predicate."""
        return (
            h3_approved is True
            and not verdict_flag(h3_rejected)
            and not verdict_flag(local_report_mode)
        )

    @staticmethod
    def _title_set(value: Any) -> set[str]:
        """Normalize a title collection without dropping caller-supplied rejections."""
        if value is None:
            return set()
        items = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
        return {str(item).strip() for item in items if str(item).strip()}

    @staticmethod
    def _new_generation_id() -> str:
        """Allocate a fresh generation identifier owned by the service."""
        return str(uuid.uuid4())

    @staticmethod
    def _pseudonymized_titles(
        titles: set[str], case_id: uuid.UUID, pseudonymizer: Any
    ) -> set[str]:
        """Return strict pseudonym forms of rejection titles, never a raw fallback."""
        rendered: set[str] = set()
        for title in titles:
            if not title:
                continue
            result = pseudonymizer.pseudonymize(title, case_id=str(case_id))
            pseudonymized = getattr(result, "pseudonymized_text", None)
            if not isinstance(pseudonymized, str) or not pseudonymized:
                raise ReportGenerationFailedException(
                    "Résultat de pseudonymisation invalide pour un titre exclu."
                )
            rendered.add(pseudonymized)
        return rendered

    def _validate_report_titles(
        self,
        bodies: str | list[str],
        case_id: uuid.UUID,
        pseudonymizer: Any | None = None,
    ) -> None:
        """Apply the drafting exclusion rule to raw text or structured section bodies."""
        from iryx.reporting.rapporteur_agent import _extract_mentioned_titles

        validated = {
            str(finding.title)
            for finding in self.db.scalars(
                select(Finding).where(
                    Finding.case_id == case_id,
                    Finding.status == FindingStatus.VALIDATED,
                )
            ).all()
            if finding.title
        }
        invalid = {
            str(finding.title)
            for finding in self.db.scalars(
                select(Finding).where(
                    Finding.case_id == case_id,
                    Finding.status != FindingStatus.VALIDATED,
                )
            ).all()
            if finding.title
        }
        exclusion = set(invalid)
        allowed = set(validated)
        if pseudonymizer is not None:
            exclusion |= self._pseudonymized_titles(invalid, case_id, pseudonymizer)
            # A validated finding may also be cited under its pseudonymized form.
            allowed |= self._pseudonymized_titles(validated, case_id, pseudonymizer)
        texts = [bodies] if isinstance(bodies, str) else bodies
        for text in texts:
            for candidate in _extract_mentioned_titles(text, exclusion, allowed):
                if candidate not in allowed:
                    raise ReportGenerationFailedException(
                        "Titre de constat non validé détecté dans le rapport."
                    )

    @staticmethod
    def _mentions_title(
        text: str, titles: set[str], allowed: set[str] | None = None
    ) -> bool:
        """Return True only for standalone unvalidated titles outside allowed ones."""
        scrubbed = text
        for title in sorted(allowed or (), key=len, reverse=True):
            if title:
                scrubbed = scrubbed.replace(title, " " * len(title))
        return any(
            title
            and re.search(r"(?<!\w)" + re.escape(title) + r"(?!\w)", scrubbed)
            for title in titles
        )

    def _allocate_version(self, case_id: uuid.UUID) -> int:
        """Compute the next version while holding the case row lock."""
        case = self.db.scalar(select(Case).where(Case.id == case_id).with_for_update())
        if case is None:
            raise ValidationException(message="Dossier introuvable.", code="CASE_NOT_FOUND")
        current = self.db.scalar(
            select(func.max(Report.version)).where(Report.case_id == case_id)
        )
        return int(current or 0) + 1

    def generate_report(
        self,
        case_id: uuid.UUID | str,
        *,
        user_id: uuid.UUID | str | None = None,
        internal: bool = False,
        h3_approved: bool | None = False,
        h3_rejected: Any = False,
        local_report_mode: Any = False,
        pseudonymizer: Any | None = None,
        llm_client: Any | None = None,
        run_id: uuid.UUID | str | None = None,
        generation_id: Any = None,
        sha256: Any = None,
        status: Any = None,
        **kwargs: Any,
    ) -> list[Report]:
        """Generate, seal and persist the Markdown/JSON pair in one transaction."""
        # Caller-supplied sealing metadata is deliberately ignored.
        del generation_id, sha256
        try:
            try:
                parsed_case_id = _safe_uuid(case_id, "case_id")
                parsed_user_id = _safe_uuid(user_id, "user_id") if user_id is not None else None
                parsed_run_id = _safe_uuid(run_id, "run_id") if run_id is not None else None
            except ValidationException as exc:
                logger.error(
                    "Report generation failed: %s",
                    type(exc).__name__,
                    extra={"context": {"case_id": "<invalid>"}},
                )
                raise ReportGenerationFailedException(
                    "Échec de génération du rapport : identifiant invalide."
                ) from exc
            rejected = verdict_flag(h3_rejected)
            local_mode = verdict_flag(local_report_mode)
            external = self._external_mode(h3_approved, h3_rejected, local_report_mode)
            if external and pseudonymizer is None:
                raise ReportGenerationFailedException(
                    "Pseudonymiseur partagé requis en mode externe."
                )
            if status is not None and ReportStatus(str(status)) is not ReportStatus.VALIDATED:
                raise ReportGenerationFailedException(
                    "Seul le statut 'validated' peut être créé par generate_report."
                )

            case = self._authorize(
                parsed_case_id, parsed_user_id, internal=internal, lock=True
            )
            if case is None:
                raise ValidationException(message="Dossier introuvable.", code="CASE_NOT_FOUND")
            context = self._load_context(case, parsed_case_id, parsed_run_id)
            # Reserved context keys come only from _load_context. A caller may add
            # invalid titles, never remove or replace the DB-derived rejection set.
            caller_titles = self._title_set(kwargs.get("invalid_finding_titles"))
            if caller_titles:
                context["invalid_finding_titles"] = sorted(
                    self._title_set(context.get("invalid_finding_titles")) | caller_titles
                )

            content = self.agent.generate_sync(
                context,
                h3_approved=h3_approved,
                h3_rejected=rejected,
                local_report_mode=local_mode,
                pseudonymizer=pseudonymizer,
                llm_client=llm_client,
            )
            invalid_titles = self._title_set(context.get("invalid_finding_titles"))
            # External documents carry pseudonymized findings: compare the sealed
            # bytes against both raw and strictly pseudonymized rejections.
            seal_titles = set(invalid_titles)
            allowed_titles = {
                str(fact["title"])
                for fact in context.get("facts", [])
                if isinstance(fact, dict) and fact.get("title")
            }
            if external and pseudonymizer is not None:
                seal_titles |= self._pseudonymized_titles(
                    invalid_titles, parsed_case_id, pseudonymizer
                )
                allowed_titles |= self._pseudonymized_titles(
                    allowed_titles, parsed_case_id, pseudonymizer
                )

            last_error: IntegrityError | None = None
            for attempt in range(_MAX_VERSION_RETRIES):
                # The sealed bytes must carry the same identity as the persisted
                # rows, so allocate all metadata before compiling this attempt.
                version = self._allocate_version(parsed_case_id)
                generation = self._new_generation_id()
                created_at = datetime.now(UTC)
                sealed_content = content.model_copy(
                    update={
                        "generation_id": uuid.UUID(generation),
                        "version": version,
                        "created_at": created_at,
                    }
                )
                compiled = compile_report(sealed_content)
                for document in compiled.documents.values():
                    if self._mentions_title(document, seal_titles, allowed_titles):
                        raise ReportGenerationFailedException(
                            "Un constat non validé a été détecté dans le rapport compilé."
                        )

                rows = [
                    Report(
                        id=uuid.uuid4(),
                        case_id=parsed_case_id,
                        format=fmt.value,
                        content=compiled.documents[fmt],
                        sha256=compiled.hashes[fmt],
                        status=ReportStatus.VALIDATED.value,
                        generation_id=generation,
                        version=version,
                        created_at=created_at,
                    )
                    for fmt in (ReportFormat.MARKDOWN, ReportFormat.JSON)
                ]
                try:
                    for row in rows:
                        self.db.add(row)
                    self.db.commit()
                    # A refresh failure after commit must never be reported as a failure.
                    with contextlib.suppress(Exception):
                        for row in rows:
                            self.db.refresh(row)
                    # The pair is already committed: a logging failure must not be
                    # reported to the caller as a generation failure.
                    with contextlib.suppress(Exception):
                        logger.info(
                            "Report generated and sealed",
                            extra={
                                "context": {
                                    "case_id": str(parsed_case_id),
                                    "generation_id": generation,
                                    "version": version,
                                    "status": ReportStatus.VALIDATED.value,
                                }
                            },
                        )
                    return rows
                except IntegrityError as exc:
                    self.db.rollback()
                    if not _is_version_conflict(exc):
                        raise ReportGenerationFailedException(
                            "Échec d'unicité inattendu lors du scellement du rapport."
                        ) from exc
                    last_error = exc
                    logger.warning(
                        "Report version conflict, retrying with a new generation",
                        extra={
                            "context": {
                                "case_id": str(parsed_case_id),
                                "attempt": attempt + 1,
                            }
                        },
                    )
            raise ReportGenerationFailedException(
                f"Impossible d'allouer une version de rapport unique : {type(last_error).__name__}."
            )
        except (
            ReportGenerationFailedException,
            InsufficientPermissionsException,
            CaseNotFoundException,
            ValidationException,
        ):
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                self.db.rollback()
            logger.error(
                "Report generation failed: %s",
                type(exc).__name__,
                extra={"context": {"case_id": str(case_id)}},
            )
            raise ReportGenerationFailedException(
                f"Échec de génération du rapport : {type(exc).__name__}."
            ) from exc

    def list_reports(
        self,
        case_id: uuid.UUID | str,
        *,
        user_id: uuid.UUID | str | None = None,
        internal: bool = False,
        format: ReportFormat | str | None = None,
    ) -> list[Report]:
        """List sealed reports strictly scoped to an authorized case."""
        try:
            parsed_case_id = _safe_uuid(case_id, "case_id")
            parsed_user_id = _safe_uuid(user_id, "user_id") if user_id is not None else None
            self._authorize(parsed_case_id, parsed_user_id, internal=internal)
            stmt = select(Report).where(Report.case_id == parsed_case_id)
            if format is not None:
                try:
                    parsed_format = ReportFormat(str(format))
                except ValueError as exc:
                    raise ValidationException(
                        message="format invalide.",
                        code="INVALID_REPORT_FORMAT",
                        status_code=422,
                    ) from exc
                stmt = stmt.where(Report.format == parsed_format.value)
            return list(
                self.db.scalars(stmt.order_by(Report.version, Report.format)).all()
            )
        except (InsufficientPermissionsException, ValidationException):
            raise
        except Exception as exc:
            logger.error(
                "Report listing failed: %s",
                type(exc).__name__,
                extra={"context": {"case_id": str(case_id)}},
            )
            raise ReportGenerationFailedException(
                f"Échec de lecture des rapports : {type(exc).__name__}."
            ) from exc

    def update_report(
        self,
        report_id: uuid.UUID | str,
        content: ReportContent | dict[str, Any] | str,
        *,
        case_id: uuid.UUID | str,
        user_id: uuid.UUID | str | None = None,
        internal: bool = False,
        pseudonymizer: Any | None = None,
        status: Any = None,
        generation_id: Any = None,
        sha256: Any = None,
    ) -> Report:
        """Update a draft only; promotion to validated/exported is forbidden."""
        del generation_id, sha256
        try:
            parsed_report_id = _safe_uuid(report_id, "report_id")
            parsed_case_id = _safe_uuid(case_id, "case_id")
            parsed_user_id = _safe_uuid(user_id, "user_id") if user_id is not None else None

            # Authorize before any report row is read, and scope every query by case.
            authorized_case = self._authorize(
                parsed_case_id, parsed_user_id, internal=internal
            )
            if authorized_case is None:
                raise ValidationException(message="Dossier introuvable.", code="CASE_NOT_FOUND")

            requested_status = (
                ReportStatus(str(status)) if status is not None else ReportStatus.DRAFT
            )
            if requested_status is not ReportStatus.DRAFT:
                raise ReportGenerationFailedException(
                    "update_report ne peut pas promouvoir un rapport."
                )

            report = self.db.scalar(
                select(Report)
                .where(
                    Report.id == parsed_report_id,
                    Report.case_id == parsed_case_id,
                    Report.status == ReportStatus.DRAFT.value,
                )
                .with_for_update()
            )
            if report is None:
                raise ReportGenerationFailedException(
                    "Rapport introuvable ou non modifiable."
                )

            bodies: str | list[str]
            if isinstance(content, str):
                rendered = content
                bodies = rendered
            else:
                structured = (
                    content
                    if isinstance(content, ReportContent)
                    else ReportContent.model_validate(content)
                )
                if structured.case_id != report.case_id:
                    raise ReportGenerationFailedException(
                        "Le contenu fourni appartient à un autre dossier."
                    )
                structured = structured.model_copy(
                    update={
                        "generation_id": uuid.UUID(str(report.generation_id)),
                        "version": report.version,
                        "created_at": report.created_at,
                    }
                )
                bodies = [section.content for section in structured.sections]
                compiled = compile_report(structured)
                rendered = compiled.documents[ReportFormat(str(report.format))]

            self._validate_report_titles(bodies, parsed_case_id, pseudonymizer)
            # Caller metadata is serialized into the final document, so the rendered
            # bytes must be checked independently of the section bodies.
            self._validate_report_titles(rendered, parsed_case_id, pseudonymizer)
            report.content = rendered
            report.sha256 = sha256_text(rendered)
            self.db.commit()
            with contextlib.suppress(Exception):
                self.db.refresh(report)
            return report
        except (
            ReportGenerationFailedException,
            InsufficientPermissionsException,
            CaseNotFoundException,
            ValidationException,
        ):
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                self.db.rollback()
            logger.error(
                "Report update failed: %s",
                type(exc).__name__,
                extra={"context": {"report_id": str(report_id)}},
            )
            raise ReportGenerationFailedException(
                f"Échec de mise à jour du rapport : {type(exc).__name__}."
            ) from exc

    @staticmethod
    def to_out(report: Report) -> ReportOut:
        """Convert a persisted row to its public representation."""
        return ReportOut(
            id=report.id,
            case_id=report.case_id,
            generation_id=report.generation_id,
            format=ReportFormat(str(report.format)),
            version=report.version,
            status=ReportStatus(str(report.status)),
            sha256=report.sha256,
            content=report.content,
            created_at=report.created_at,
        )
