"""Deterministic Multi-Source Timeline Correlator (Story 7.3, Invariant 2).

This module implements the deterministic correlation engine that superimposes
validated investigation findings (Gate H2) onto source observations and detects
multi-source correlations (distinct tools or distinct evidence sources).

Strict adherence to Invariant 2: Pure in-memory calculation; no timeline events
are created, updated, or forged in the database.
"""

import contextlib
import logging
import uuid
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from iryx.analytics.models import Finding, FindingStatus, Observation
from iryx.analytics.schemas import (
    CorrelationGroupOut,
    TimelineCorrelationsResponse,
    TimelineEventOut,
    TimelineFactBase,
    TimelineFindingRef,
    UndatedFactOut,
)
from iryx.evidence.models import Evidence

logger = logging.getLogger("iryx.analytics.correlator")


class TimelineCorrelator:
    """Deterministic correlation and finding overlay engine (FR24, Invariant 2).

    1. Superimposes validated findings (Gate H2) onto source timeline events.
    2. Excludes strictly findings with status PROPOSED or REJECTED.
    3. Detects multi-source correlations when a validated finding links observations
       from distinct tools (`tool_name`) or distinct evidence sources (`source_id`).
    4. Assigns a shared visual correlation marker `f"corr-{finding.id}"` and sets
       `is_correlated = True` for participating events.
    5. Enforces strict multi-tenant case isolation (Zero Leak).
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._cache: dict[
            uuid.UUID,
            tuple[
                dict[uuid.UUID, list[TimelineFindingRef]],
                dict[uuid.UUID, list[str]],
                set[uuid.UUID],
                list[dict[str, Any]],
            ],
        ] = {}

    def get_validated_findings(self, case_id: uuid.UUID) -> Sequence[Finding]:
        """Fetch all validated findings strictly scoped to the given case_id."""
        stmt = (
            select(Finding)
            .where(
                Finding.case_id == case_id,
                Finding.status == FindingStatus.VALIDATED,
            )
            .order_by(Finding.created_at.asc(), Finding.id.asc())
        )
        return self.db.scalars(stmt).all()

    def build_correlation_metadata(
        self, case_id: uuid.UUID
    ) -> tuple[
        dict[uuid.UUID, list[TimelineFindingRef]],
        dict[uuid.UUID, list[str]],
        set[uuid.UUID],
        list[dict[str, Any]],
    ]:
        """Compute finding superposition and multi-source correlation index.

        Returns:
            - obs_findings: mapping observation_id -> list of TimelineFindingRef
            - obs_markers: mapping observation_id -> list of correlation markers (e.g. ['corr-...'])
            - correlated_obs_ids: set of observation_ids that are part of a multi-source correlation
            - correlation_groups_data: list of raw group data for CorrelationGroupOut
        """
        if case_id in self._cache:
            return self._cache[case_id]

        findings = self.get_validated_findings(case_id)
        if not findings:
            self._cache[case_id] = ({}, {}, set(), [])
            return self._cache[case_id]

        # Gather all observation UUIDs referenced by validated findings
        all_obs_refs: set[uuid.UUID] = set()
        for f in findings:
            if f.observation_refs:
                for r in f.observation_refs:
                    if isinstance(r, uuid.UUID):
                        all_obs_refs.add(r)
                    else:
                        with contextlib.suppress(ValueError, TypeError):
                            all_obs_refs.add(uuid.UUID(str(r)))

        if not all_obs_refs:
            self._cache[case_id] = ({}, {}, set(), [])
            return self._cache[case_id]

        # Fetch all referenced observations strictly scoped to case_id
        stmt = (
            select(Observation, Evidence.original_name)
            .outerjoin(Evidence, Observation.source_id == Evidence.id)
            .where(
                Observation.id.in_(list(all_obs_refs)),
                Observation.case_id == case_id,
            )
            .order_by(Observation.timestamp_utc.asc().nulls_last(), Observation.id.asc())
        )
        obs_rows = self.db.execute(stmt).all()
        obs_dict: dict[uuid.UUID, tuple[Observation, str | None]] = {
            obs.id: (obs, ev_name) for obs, ev_name in obs_rows
        }

        # Import mapping helpers outside the findings loop
        from iryx.analytics.services import (
            _extract_technical_summary,
            _map_observation_to_event,
        )

        obs_findings: dict[uuid.UUID, list[TimelineFindingRef]] = defaultdict(list)
        obs_markers: dict[uuid.UUID, list[str]] = defaultdict(list)
        correlated_obs_ids: set[uuid.UUID] = set()
        correlation_groups_data: list[dict[str, Any]] = []

        for f in findings:
            ref = TimelineFindingRef(
                id=f.id,
                title=f.title,
                severity=f.severity,
                confidence=f.confidence,
                finding_type=f.finding_type,
            )
            marker = f"corr-{f.id}"

            # Observations belonging to this finding that exist in this case (deduplicated)
            f_obs_tuples: list[tuple[Observation, str | None]] = []
            f_obs_ids: set[uuid.UUID] = set()
            seen_refs: set[uuid.UUID] = set()
            for r in f.observation_refs or []:
                if isinstance(r, uuid.UUID):
                    parsed_id = r
                else:
                    try:
                        parsed_id = uuid.UUID(str(r))
                    except (ValueError, TypeError):
                        continue
                if parsed_id not in seen_refs:
                    seen_refs.add(parsed_id)
                    if parsed_id in obs_dict:
                        f_obs_tuples.append(obs_dict[parsed_id])
                        f_obs_ids.add(parsed_id)

            # Superimpose finding onto every referenced observation
            for oid in f_obs_ids:
                if not any(existing.id == ref.id for existing in obs_findings[oid]):
                    obs_findings[oid].append(ref)

            # Check multi-source correlation criteria:
            # - At least two observations
            # - Distinct tools (tool_name) OR distinct sources (source_id)
            tools = {obs.tool_name for obs, _ in f_obs_tuples if obs.tool_name}
            sources = {obs.source_id for obs, _ in f_obs_tuples if obs.source_id is not None}
            is_multi_tool = len(tools) >= 2
            is_multi_source = len(sources) >= 2

            if len(f_obs_tuples) >= 2 and (is_multi_tool or is_multi_source):
                for oid in f_obs_ids:
                    correlated_obs_ids.add(oid)
                    if marker not in obs_markers[oid]:
                        obs_markers[oid].append(marker)

                # Prepare group data
                dated_events: list[TimelineEventOut] = []
                undated_events: list[UndatedFactOut] = []
                for obs, ev_name in f_obs_tuples:
                    evt = _map_observation_to_event(obs, ev_name)
                    if evt is not None:
                        evt.findings = [ref]
                        evt.correlation_marker = marker
                        evt.correlation_id = marker
                        evt.correlation_markers = [marker]
                        evt.is_correlated = True
                        dated_events.append(evt)
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
                                evidence_name=ev_name,
                                summary=summary,
                                source_location=obs.source_location,
                                details=details,
                                timestamp_utc=None,
                                findings=[ref],
                                correlation_marker=marker,
                                correlation_id=marker,
                                correlation_markers=[marker],
                                is_correlated=True,
                            )
                        )

                dated_events.sort(key=lambda e: (e.timestamp_utc, e.observation_id))
                start_time = dated_events[0].timestamp_utc if dated_events else None
                end_time = dated_events[-1].timestamp_utc if dated_events else None
                time_span = (
                    (end_time - start_time).total_seconds() if (start_time and end_time) else 0.0
                )

                group_data = {
                    "correlation_marker": marker,
                    "correlation_id": marker,
                    "finding_id": f.id,
                    "finding_title": f.title,
                    "finding": ref,
                    "events": dated_events,
                    "undated_events": undated_events,
                    "tools": sorted(list(tools)),
                    "sources": sorted(list(sources), key=lambda u: str(u)),
                    "evidence_ids": sorted(list(sources), key=lambda u: str(u)),
                    "total_events": len(dated_events),
                    "events_count": len(dated_events),
                    "total_undated": len(undated_events),
                    "start_time": start_time,
                    "end_time": end_time,
                    "time_span_seconds": time_span,
                    "is_multi_tool": is_multi_tool,
                    "is_multi_source": is_multi_source,
                }
                correlation_groups_data.append(group_data)

        self._cache[case_id] = (
            obs_findings,
            obs_markers,
            correlated_obs_ids,
            correlation_groups_data,
        )
        return self._cache[case_id]

    def enrich_events(
        self,
        events: Sequence[TimelineFactBase],
        undated_events: Sequence[UndatedFactOut] | None = None,
        case_id: uuid.UUID | None = None,
    ) -> Sequence[TimelineFactBase]:
        """Enrich in-memory timeline and undated events with superposition and correlations."""
        if case_id is None:
            # Nothing to enrich if case_id is unknown
            return events

        obs_findings, obs_markers, correlated_obs_ids, _ = self.build_correlation_metadata(case_id)

        for event in events:
            oid = event.observation_id
            event.findings = list(obs_findings.get(oid, []))
            markers = list(obs_markers.get(oid, []))
            event.correlation_markers = markers
            event.correlation_marker = markers[0] if markers else None
            event.correlation_id = markers[0] if markers else None
            event.is_correlated = oid in correlated_obs_ids

        if undated_events is not None:
            for undated in undated_events:
                oid = undated.observation_id
                undated.findings = list(obs_findings.get(oid, []))
                markers = list(obs_markers.get(oid, []))
                undated.correlation_markers = markers
                undated.correlation_marker = markers[0] if markers else None
                undated.correlation_id = markers[0] if markers else None
                undated.is_correlated = oid in correlated_obs_ids

        return events

    # Public alias
    correlate_events = enrich_events

    def get_case_correlations(self, case_id: uuid.UUID) -> TimelineCorrelationsResponse:
        """Retrieve structured multi-source correlation groups for a case."""
        _, _, _, groups_data = self.build_correlation_metadata(case_id)
        groups = [CorrelationGroupOut(**gd) for gd in groups_data]
        return TimelineCorrelationsResponse(
            case_id=case_id,
            correlations=groups,
            groups=groups,
            items=groups,
            total=len(groups),
            total_groups=len(groups),
        )
