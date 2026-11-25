"""IRYX Analytics and Finding Business Services."""

import contextlib
import json
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iryx.analytics.models import (
    Finding,
    FindingConfidence,
    FindingSeverity,
    FindingStatus,
    FindingType,
    Observation,
)
from iryx.analytics.schemas import (
    FindingCreate,
    FindingReview,
    FindingUpdate,
    TimelineCorrelationsResponse,
    TimelineEventOut,
    TimelineListResponse,
    TimelineProjectionResponse,
    UndatedFactOut,
)
from iryx.core.exceptions import FindingNotFoundException, ValidationException
from iryx.evidence.models import Evidence

logger = logging.getLogger("iryx.analytics.services")


class FindingService:
    """Service encapsulating CRUD and persistence operations for investigation findings."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_finding(
        self,
        case_id: uuid.UUID,
        payload: FindingCreate,
        created_by: uuid.UUID | None = None,
    ) -> Finding:
        """Create and persist a new technical finding with status 'proposed'."""
        finding = Finding(
            case_id=case_id,
            title=payload.title,
            severity=payload.severity,
            confidence=payload.confidence,
            finding_type=payload.finding_type,
            status=FindingStatus.PROPOSED,
            observation_refs=list(payload.observation_refs),
            tool_execution_refs=list(payload.tool_execution_refs),
            created_by=created_by,
        )
        self.db.add(finding)
        self.db.commit()
        self.db.refresh(finding)
        return finding

    def get_finding(self, case_id: uuid.UUID, finding_id: uuid.UUID) -> Finding:
        """Retrieve a single finding by ID scoped to the given case."""
        stmt = select(Finding).where(Finding.id == finding_id, Finding.case_id == case_id)
        finding = self.db.scalar(stmt)
        if finding is None:
            raise FindingNotFoundException()
        return finding

    def list_findings(
        self,
        case_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
        status: FindingStatus | None = None,
        severity: FindingSeverity | None = None,
        confidence: FindingConfidence | None = None,
        finding_type: FindingType | None = None,
    ) -> tuple[Sequence[Finding], int]:
        """List paginated findings belonging to a case with deterministic sorting and filtering."""
        stmt = select(Finding).where(Finding.case_id == case_id)
        count_stmt = select(func.count(Finding.id)).where(Finding.case_id == case_id)

        if status is not None:
            stmt = stmt.where(Finding.status == status)
            count_stmt = count_stmt.where(Finding.status == status)

        if severity is not None:
            stmt = stmt.where(Finding.severity == severity)
            count_stmt = count_stmt.where(Finding.severity == severity)

        if confidence is not None:
            stmt = stmt.where(Finding.confidence == confidence)
            count_stmt = count_stmt.where(Finding.confidence == confidence)

        if finding_type is not None:
            stmt = stmt.where(Finding.finding_type == finding_type)
            count_stmt = count_stmt.where(Finding.finding_type == finding_type)

        total = self.db.scalar(count_stmt) or 0
        items = self.db.scalars(
            stmt.order_by(Finding.created_at.desc(), Finding.id.desc()).offset(offset).limit(limit)
        ).all()

        return items, total

    def update_finding(
        self,
        case_id: uuid.UUID,
        finding_id: uuid.UUID,
        payload: FindingUpdate,
    ) -> Finding:
        """Update fields of an existing finding scoped to the given case."""
        finding = self.get_finding(case_id=case_id, finding_id=finding_id)

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field in ("observation_refs", "tool_execution_refs") and value is not None:
                setattr(finding, field, list(value))
            elif value is not None:
                setattr(finding, field, value)

        self.db.commit()
        self.db.refresh(finding)
        return finding

    def delete_finding(self, case_id: uuid.UUID, finding_id: uuid.UUID) -> None:
        """Delete an existing finding scoped to the given case."""
        finding = self.get_finding(case_id=case_id, finding_id=finding_id)
        self.db.delete(finding)
        self.db.commit()

    def review_finding(
        self,
        case_id: uuid.UUID,
        finding_id: uuid.UUID,
        payload: FindingReview,
        user_id: uuid.UUID | None = None,
    ) -> Finding:
        """Apply human-in-the-loop review decision to a finding (Story 6.4, FR19)."""
        stmt = (
            select(Finding)
            .where(Finding.id == finding_id, Finding.case_id == case_id)
            .with_for_update()
        )
        finding = self.db.scalar(stmt)
        if finding is None:
            raise FindingNotFoundException()

        if payload.action not in ("validate", "reject"):
            raise ValidationException(
                message=f"Action de revue invalide : '{payload.action}'.",
                code="INVALID_REVIEW_ACTION",
            )

        if payload.action == "validate":
            finding.status = FindingStatus.VALIDATED
            if payload.severity is not None:
                finding.severity = payload.severity
            if payload.confidence is not None:
                finding.confidence = payload.confidence
        elif payload.action == "reject":
            finding.status = FindingStatus.REJECTED

        if user_id is not None:
            finding.created_by = user_id

        self.db.commit()
        self.db.refresh(finding)
        return finding


def _extract_technical_summary(normalized_content: Any) -> str:
    """Extract a concise human-readable technical summary from normalized observation content."""
    try:
        if not normalized_content:
            return "Observation fact"

        if isinstance(normalized_content, str):
            cleaned = normalized_content.strip()
            return cleaned[:255] if cleaned else "Observation fact"

        if not isinstance(normalized_content, dict):
            return json.dumps(normalized_content, default=str)[:255]

        has_meaningful_content = any(
            (v.strip() if isinstance(v, str) else v is not None)
            for v in normalized_content.values()
        )
        if not has_meaningful_content:
            return "Observation fact"

        # 1. Priority fields specified by architecture & domain standards
        priority_keys = (
            "summary",
            "message",
            "description",
            "event_description",
            "command_line",
        )
        for key in priority_keys:
            val = normalized_content.get(key)
            if val is not None:
                if isinstance(val, str) and val.strip():
                    return val.strip()[:255]
                elif isinstance(val, (int, float, bool)):
                    return f"{key}: {val}"
                elif isinstance(val, (dict, list)):
                    return json.dumps(val, default=str)[:255]

        # 2. Domain-specific DFIR fallbacks (EVTX, Registry, Prefetch, Memory)
        if "event_id" in normalized_content or "EventID" in normalized_content:
            eid = (
                normalized_content.get("event_id")
                if normalized_content.get("event_id") is not None
                else normalized_content.get("EventID")
            )
            if eid is not None:
                channel = normalized_content.get("channel")
                if channel:
                    return f"Event {eid} ({channel})"[:255]
                return f"Event {eid}"

        if "process_name" in normalized_content or "executable_name" in normalized_content:
            proc = normalized_content.get("process_name") or normalized_content.get(
                "executable_name"
            )
            pid = normalized_content.get("pid")
            if pid is not None:
                return f"Process {proc} (PID {pid})"[:255]
            return f"Process {proc}"[:255]

        if "command" in normalized_content and normalized_content["command"] is not None:
            cmd_str = str(normalized_content["command"]).strip()
            if cmd_str:
                return cmd_str[:255]

        if "key_path" in normalized_content or "key" in normalized_content:
            k = normalized_content.get("key_path") or normalized_content.get("key")
            return f"Registry: {k}"[:255]

        raw = normalized_content.get("raw")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()[:255]

        # 3. Compact key-value fallback
        condensed_parts: list[str] = []
        for k, v in normalized_content.items():
            if isinstance(v, str) and not v.strip():
                continue
            if isinstance(v, (str, int, float, bool)):
                condensed_parts.append(f"{k}={v}")
            if len(condensed_parts) >= 3:
                break
        if condensed_parts:
            return ", ".join(condensed_parts)[:255]

        dumped = json.dumps(normalized_content, default=str)
        return dumped[:255] if dumped != "{}" else "Observation fact"

    except Exception:
        return "Observation fact"


# Public alias
extract_technical_summary = _extract_technical_summary


def _get_timeline_correlator(db: Session) -> Any:
    """Lazy import of TimelineCorrelator to avoid circular imports during module load."""
    from iryx.analytics.correlator import TimelineCorrelator

    return TimelineCorrelator(db)


def _map_observation_to_event(
    obs: Observation, evidence_name: str | None = None
) -> TimelineEventOut | None:
    """Map an Observation ORM entity with valid timestamp to a TimelineEventOut schema."""
    summary = _extract_technical_summary(obs.normalized_content)
    if isinstance(obs.normalized_content, dict):
        details = obs.normalized_content
    elif obs.normalized_content is not None:
        details = {"raw": obs.normalized_content}
    else:
        details = {}

    ts = obs.timestamp_utc
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            ts = None

    if ts is None:
        return None

    ts = ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
    return TimelineEventOut(
        timestamp_utc=ts,
        observation_id=obs.id,
        tool_name=obs.tool_name,
        tool_execution_id=obs.tool_execution_id,
        evidence_id=obs.source_id,
        evidence_name=evidence_name,
        summary=summary,
        source_location=obs.source_location,
        details=details,
    )


class _TimelineProjectionDispatcher:
    """Descriptor enabling get_timeline_projection on class or instance."""

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        def dispatcher(*args: Any, **kwargs: Any) -> TimelineProjectionResponse:
            target_db: Session | None = None
            target_case_id: uuid.UUID | None = None

            if instance is not None:
                # Invocation on instance: svc.get_timeline_projection(...)
                target_db = getattr(instance, "db", None)
                if len(args) == 2 and isinstance(args[0], Session):
                    target_db = args[0]
                    target_case_id = args[1]
                elif len(args) == 1:
                    if isinstance(args[0], Session):
                        target_db = args[0]
                    else:
                        target_case_id = args[0]
                elif len(args) == 0:
                    pass
                else:
                    msg = f"Too many arguments passed to get_timeline_projection: {len(args)}"
                    raise TypeError(msg)

                if "db" in kwargs:
                    target_db = kwargs["db"]
                if "case_id" in kwargs:
                    target_case_id = kwargs["case_id"]

            else:
                # Invocation on class: TimelineService.get_timeline_projection(...)
                if len(args) == 2:
                    target_db = args[0]
                    target_case_id = args[1]
                elif len(args) == 1:
                    if isinstance(args[0], Session):
                        target_db = args[0]
                    else:
                        target_case_id = args[0]
                elif len(args) == 0:
                    pass
                else:
                    msg = f"Too many arguments passed to get_timeline_projection: {len(args)}"
                    raise TypeError(msg)

                if "db" in kwargs:
                    target_db = kwargs["db"]
                if "case_id" in kwargs:
                    target_case_id = kwargs["case_id"]

            if target_db is None:
                raise ValueError("Database session (db) is required.")
            if target_case_id is None:
                raise ValueError("Case ID (case_id) is required.")

            target_cls = owner if owner is not None else TimelineService
            return target_cls._execute_timeline_projection(
                db=target_db,
                case_id=target_case_id,
            )

        dispatcher.__doc__ = (
            "Compute unified deterministic timeline projection for case (FR24, Invariant 2)."
        )
        return dispatcher


class _PaginatedTimelineDispatcher:
    """Descriptor enabling get_paginated_timeline on class or instance."""

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        def dispatcher(*args: Any, **kwargs: Any) -> TimelineListResponse:
            target_db: Session | None = None
            pos_args = list(args)

            if pos_args and isinstance(pos_args[0], Session):
                target_db = pos_args.pop(0)
            elif instance is not None:
                target_db = getattr(instance, "db", None)

            if "db" in kwargs:
                target_db = kwargs.pop("db")

            param_names = [
                "case_id",
                "limit",
                "offset",
                "start_time",
                "end_time",
                "tool_name",
                "evidence_id",
                "is_correlated",
                "correlation_marker",
                "finding_id",
            ]
            for idx, val in enumerate(pos_args):
                if idx < len(param_names):
                    name = param_names[idx]
                    if name not in kwargs:
                        kwargs[name] = val

            target_case_id = kwargs.pop("case_id", None)
            if target_db is None:
                raise ValueError("Database session (db) is required.")
            if target_case_id is None:
                raise ValueError("Case ID (case_id) is required.")

            limit = kwargs.pop("limit", 50)
            offset = kwargs.pop("offset", 0)
            start_time = kwargs.pop("start_time", None)
            end_time = kwargs.pop("end_time", None)
            tool_name = kwargs.pop("tool_name", None)
            evidence_id = kwargs.pop("evidence_id", None)
            is_correlated = kwargs.pop("is_correlated", None)
            correlation_marker = kwargs.pop("correlation_marker", None)
            finding_id = kwargs.pop("finding_id", None)

            target_cls = owner if owner is not None else TimelineService
            return target_cls._execute_paginated_timeline(
                db=target_db,
                case_id=target_case_id,
                limit=limit,
                offset=offset,
                start_time=start_time,
                end_time=end_time,
                tool_name=tool_name,
                evidence_id=evidence_id,
                is_correlated=is_correlated,
                correlation_marker=correlation_marker,
                finding_id=finding_id,
            )

        dispatcher.__doc__ = (
            "Retrieve paginated chronological timeline events for case (Story 7.2, NFR-PERF-07)."
        )
        return dispatcher


class _CaseCorrelationsDispatcher:
    """Descriptor enabling get_case_correlations on class or instance (Story 7.3)."""

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        def dispatcher(*args: Any, **kwargs: Any) -> TimelineCorrelationsResponse:
            target_db: Session | None = None
            pos_args = list(args)

            if pos_args and isinstance(pos_args[0], Session):
                target_db = pos_args.pop(0)
            elif instance is not None:
                target_db = getattr(instance, "db", None)

            if "db" in kwargs:
                target_db = kwargs.pop("db")

            target_case_id = kwargs.pop("case_id", None)
            if pos_args and target_case_id is None:
                target_case_id = pos_args.pop(0)

            if target_db is None:
                raise ValueError("Database session (db) is required.")
            if target_case_id is None:
                raise ValueError("Case ID (case_id) is required.")

            target_cls = owner if owner is not None else TimelineService
            return target_cls._execute_case_correlations(
                db=target_db,
                case_id=target_case_id,
            )

        dispatcher.__doc__ = (
            "Retrieve structured multi-source correlation groups for a case (Story 7.3)."
        )
        return dispatcher


class TimelineService:
    """Service governing deterministic unified timeline projections (FR24, Invariant 2).

    This service is a pure read-only projection mechanism. In strict adherence to Invariant 2,
    no mutable timeline persistence table exists, and no methods exist to forge, create,
    update, or delete temporal events.
    """

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    get_timeline_projection = _TimelineProjectionDispatcher()
    get_paginated_timeline = _PaginatedTimelineDispatcher()
    get_case_correlations = _CaseCorrelationsDispatcher()

    @classmethod
    def _execute_timeline_projection(
        cls,
        db: Session,
        case_id: uuid.UUID | str,
    ) -> TimelineProjectionResponse:
        """Compute the deterministic chronological projection for a case in ascending UTC order."""
        if not isinstance(case_id, uuid.UUID):
            try:
                parsed_case_id = uuid.UUID(str(case_id))
            except (ValueError, TypeError, AttributeError) as exc:
                msg = f"Invalid case_id format: {case_id}"
                raise ValueError(msg) from exc
        else:
            parsed_case_id = case_id

        stmt = (
            select(Observation, Evidence.original_name)
            .outerjoin(Evidence, Observation.source_id == Evidence.id)
            .where(Observation.case_id == parsed_case_id)
            .order_by(Observation.timestamp_utc.asc().nulls_last(), Observation.id.asc())
        )
        rows = db.execute(stmt).all()

        events: list[TimelineEventOut] = []
        undated_events: list[UndatedFactOut] = []

        for obs, evidence_name in rows:
            event = _map_observation_to_event(obs, evidence_name)
            if event is not None:
                events.append(event)
            else:
                summary = _extract_technical_summary(obs.normalized_content)
                details = (
                    obs.normalized_content
                    if isinstance(obs.normalized_content, dict)
                    else (
                        {"raw": obs.normalized_content}
                        if obs.normalized_content is not None
                        else {}
                    )
                )
                undated_events.append(
                    UndatedFactOut(
                        observation_id=obs.id,
                        tool_name=obs.tool_name,
                        tool_execution_id=obs.tool_execution_id,
                        evidence_id=obs.source_id,
                        evidence_name=evidence_name,
                        summary=summary,
                        source_location=obs.source_location,
                        details=details,
                        timestamp_utc=None,
                    )
                )

        correlator = _get_timeline_correlator(db)
        correlator.enrich_events(
            events=events,
            undated_events=undated_events,
            case_id=parsed_case_id,
        )

        return TimelineProjectionResponse(
            case_id=parsed_case_id,
            events=events,
            undated_events=undated_events,
            total_events=len(events),
            total_undated=len(undated_events),
        )

    @classmethod
    def _execute_paginated_timeline(
        cls,
        db: Session,
        case_id: uuid.UUID | str,
        limit: int = 50,
        offset: int = 0,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        tool_name: str | None = None,
        evidence_id: uuid.UUID | None = None,
        is_correlated: bool | None = None,
        correlation_marker: str | None = None,
        finding_id: uuid.UUID | None = None,
    ) -> TimelineListResponse:
        """Execute paginated timeline query using composite index (case_id, timestamp_utc)."""
        if not isinstance(case_id, uuid.UUID):
            try:
                parsed_case_id = uuid.UUID(str(case_id))
            except (ValueError, TypeError, AttributeError) as exc:
                msg = f"Invalid case_id format: {case_id}"
                raise ValueError(msg) from exc
        else:
            parsed_case_id = case_id

        st: datetime | None = None
        et: datetime | None = None
        if start_time is not None:
            st = (
                start_time.replace(tzinfo=UTC)
                if start_time.tzinfo is None
                else start_time.astimezone(UTC)
            )
        if end_time is not None:
            et = (
                end_time.replace(tzinfo=UTC)
                if end_time.tzinfo is None
                else end_time.astimezone(UTC)
            )

        if st is not None and et is not None and st > et:
            raise ValidationException(
                message="start_time must be before end_time",
                code="VALIDATION_ERROR",
            )

        sanitized_tool_name = tool_name.strip() if tool_name and tool_name.strip() else None
        correlator = _get_timeline_correlator(db)

        stmt = (
            select(Observation, Evidence.original_name)
            .outerjoin(Evidence, Observation.source_id == Evidence.id)
            .where(
                Observation.case_id == parsed_case_id,
                Observation.timestamp_utc.is_not(None),
            )
        )
        count_stmt = select(func.count(Observation.id)).where(
            Observation.case_id == parsed_case_id,
            Observation.timestamp_utc.is_not(None),
        )

        if st is not None:
            stmt = stmt.where(Observation.timestamp_utc >= st)
            count_stmt = count_stmt.where(Observation.timestamp_utc >= st)

        if et is not None:
            stmt = stmt.where(Observation.timestamp_utc <= et)
            count_stmt = count_stmt.where(Observation.timestamp_utc <= et)

        if sanitized_tool_name is not None:
            stmt = stmt.where(Observation.tool_name == sanitized_tool_name)
            count_stmt = count_stmt.where(Observation.tool_name == sanitized_tool_name)

        if evidence_id is not None:
            stmt = stmt.where(Observation.source_id == evidence_id)
            count_stmt = count_stmt.where(Observation.source_id == evidence_id)

        if finding_id is not None:
            f = db.scalar(
                select(Finding).where(
                    Finding.id == finding_id,
                    Finding.case_id == parsed_case_id,
                    Finding.status == FindingStatus.VALIDATED,
                )
            )
            raw_refs = list(f.observation_refs) if f and f.observation_refs else []
            obs_refs: list[uuid.UUID] = []
            for r in raw_refs:
                if isinstance(r, uuid.UUID):
                    obs_refs.append(r)
                else:
                    with contextlib.suppress(ValueError, TypeError):
                        obs_refs.append(uuid.UUID(str(r)))
            if not obs_refs:
                return TimelineListResponse(
                    items=[],
                    events=[],
                    total=0,
                    total_items=0,
                    limit=limit,
                    offset=offset,
                    has_more=False,
                )
            stmt = stmt.where(Observation.id.in_(obs_refs))
            count_stmt = count_stmt.where(Observation.id.in_(obs_refs))

        if correlation_marker is not None:
            marker_str = correlation_marker.strip()
            _, obs_markers, _, _ = correlator.build_correlation_metadata(parsed_case_id)
            marker_obs_ids = [oid for oid, markers in obs_markers.items() if marker_str in markers]
            if not marker_obs_ids:
                return TimelineListResponse(
                    items=[],
                    events=[],
                    total=0,
                    total_items=0,
                    limit=limit,
                    offset=offset,
                    has_more=False,
                )
            stmt = stmt.where(Observation.id.in_(marker_obs_ids))
            count_stmt = count_stmt.where(Observation.id.in_(marker_obs_ids))

        if is_correlated is not None:
            _, _, correlated_obs_ids, _ = correlator.build_correlation_metadata(parsed_case_id)
            if is_correlated is True:
                if not correlated_obs_ids:
                    return TimelineListResponse(
                        items=[],
                        events=[],
                        total=0,
                        total_items=0,
                        limit=limit,
                        offset=offset,
                        has_more=False,
                    )
                stmt = stmt.where(Observation.id.in_(list(correlated_obs_ids)))
                count_stmt = count_stmt.where(Observation.id.in_(list(correlated_obs_ids)))
            else:
                if correlated_obs_ids:
                    stmt = stmt.where(Observation.id.not_in(list(correlated_obs_ids)))
                    count_stmt = count_stmt.where(Observation.id.not_in(list(correlated_obs_ids)))

        total = db.scalar(count_stmt) or 0

        # Avoid redundant query when total == 0 or offset >= total
        if total == 0 or offset >= total:
            return TimelineListResponse(
                items=[],
                events=[],
                total=total,
                total_items=total,
                limit=limit,
                offset=offset,
                has_more=False,
            )

        stmt = (
            stmt.order_by(Observation.timestamp_utc.asc(), Observation.id.asc())
            .limit(limit)
            .offset(offset)
        )
        rows = db.execute(stmt).all()

        events: list[TimelineEventOut] = []
        for obs, evidence_name in rows:
            event = _map_observation_to_event(obs, evidence_name)
            if event is not None:
                events.append(event)

        correlator.enrich_events(events=events, case_id=parsed_case_id)

        has_more = (offset + len(events)) < total

        return TimelineListResponse(
            items=events,
            events=events,
            total=total,
            total_items=total,
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    @classmethod
    def _execute_case_correlations(
        cls,
        db: Session,
        case_id: uuid.UUID | str,
    ) -> TimelineCorrelationsResponse:
        """Execute deterministic multi-source correlation calculation for case (Story 7.3)."""
        if not isinstance(case_id, uuid.UUID):
            try:
                parsed_case_id = uuid.UUID(str(case_id))
            except (ValueError, TypeError, AttributeError) as exc:
                msg = f"Invalid case_id format: {case_id}"
                raise ValueError(msg) from exc
        else:
            parsed_case_id = case_id

        correlator = _get_timeline_correlator(db)
        return correlator.get_case_correlations(case_id=parsed_case_id)
