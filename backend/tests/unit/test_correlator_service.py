"""Unit tests for deterministic TimelineCorrelator engine (Story 7.3, Invariant 2)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iryx.analytics.correlator import TimelineCorrelator
from iryx.analytics.models import (
    Finding,
    FindingConfidence,
    FindingSeverity,
    FindingStatus,
    FindingType,
    Observation,
)
from iryx.analytics.schemas import TimelineCorrelationsResponse
from iryx.analytics.services import TimelineService
from iryx.auth.models import Organization, User
from iryx.cases.models import Case
from iryx.evidence.models import Evidence


@pytest.fixture
def test_organization(db_session: Session) -> Organization:
    """Create test organization."""
    org = Organization(name="CERT Investigation Unit")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create test user."""
    user = User(email=f"analyst-{uuid.uuid4()}@cert.gov", hashed_password="pw")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_case(db_session: Session, test_organization: Organization, test_user: User) -> Case:
    """Create a primary test case."""
    case = Case(
        id=uuid.uuid4(),
        organization_id=test_organization.id,
        title="DFIR Correlation Test Case",
        description="Case for testing multi-source correlation engine",
        created_by=test_user.id,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


@pytest.fixture
def other_case(db_session: Session, test_organization: Organization, test_user: User) -> Case:
    """Create an isolated secondary test case for multi-tenant verification."""
    case = Case(
        id=uuid.uuid4(),
        organization_id=test_organization.id,
        title="Other Case",
        description="Case for tenant isolation verification",
        created_by=test_user.id,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


@pytest.fixture
def test_evidence(db_session: Session, test_case: Case) -> Evidence:
    """Create sealed primary digital evidence."""
    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=test_case.id,
        original_name="Security.evtx",
        file_size=1024 * 1024,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        detected_type="application/x-winevtx",
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)
    return evidence


@pytest.fixture
def second_evidence(db_session: Session, test_case: Case) -> Evidence:
    """Create sealed secondary digital evidence."""
    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=test_case.id,
        original_name="Prefetch_CALC.pf",
        file_size=512 * 1024,
        sha256="a" * 64,
        detected_type="application/x-prefetch",
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)
    return evidence


class TestTimelineCorrelatorUnit:
    """Unit tests for deterministic correlation engine logic."""

    def test_empty_case_correlations(self, db_session: Session, test_case: Case) -> None:
        """Given a case with no findings, then correlations response is empty."""
        correlator = TimelineCorrelator(db_session)
        resp = correlator.get_case_correlations(test_case.id)

        assert isinstance(resp, TimelineCorrelationsResponse)
        assert resp.case_id == test_case.id
        assert resp.total == 0
        assert resp.total_groups == 0
        assert resp.correlations == []
        assert resp.groups == []
        assert resp.items == []

    def test_nominal_multi_sources_correlation(
        self,
        db_session: Session,
        test_case: Case,
        test_evidence: Evidence,
        second_evidence: Evidence,
    ) -> None:
        """Given a validated finding linking Prefetch and EVTX at the same minute,

        then events receive the shared correlation marker and is_correlated=True.
        """
        base_time = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)

        obs_prefetch = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="dissect",
            source_id=second_evidence.id,
            source_location=r"C:\Windows\Prefetch\MALWARE.EXE-12345.pf",
            normalized_content={"executable_name": "MALWARE.EXE", "run_count": 1},
            timestamp_utc=base_time,
        )
        obs_evtx = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            source_location="Event 4688",
            normalized_content={"event_id": 4688, "process_name": "MALWARE.EXE"},
            timestamp_utc=base_time + timedelta(seconds=30),
        )
        db_session.add_all([obs_prefetch, obs_evtx])
        db_session.commit()

        # Create validated finding referencing both observations
        finding = Finding(
            id=uuid.uuid4(),
            case_id=test_case.id,
            title="Execution of MALWARE.EXE detected via Prefetch and Security EVTX",
            severity=FindingSeverity.HIGH,
            confidence=FindingConfidence.HIGH,
            finding_type=FindingType.FACT,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs_prefetch.id, obs_evtx.id],
            tool_execution_refs=[],
        )
        db_session.add(finding)
        db_session.commit()

        # 1. Test get_case_correlations
        correlator = TimelineCorrelator(db_session)
        corr_resp = correlator.get_case_correlations(test_case.id)

        assert corr_resp.total == 1
        group = corr_resp.correlations[0]
        expected_marker = f"corr-{finding.id}"
        assert group.correlation_marker == expected_marker
        assert group.correlation_id == expected_marker
        assert group.finding_id == finding.id
        assert group.finding_title == finding.title
        assert group.is_multi_tool is True
        assert group.is_multi_source is True
        assert group.tools == ["dissect", "python-evtx"]
        assert len(group.events) == 2
        assert group.total_events == 2
        assert group.start_time == base_time
        assert group.end_time == base_time + timedelta(seconds=30)
        assert group.time_span_seconds == 30.0

        # Verify dated events inside group
        for evt in group.events:
            assert evt.correlation_marker == expected_marker
            assert evt.is_correlated is True
            assert len(evt.findings) == 1
            assert evt.findings[0].id == finding.id
            assert evt.findings[0].title == finding.title

        # 2. Test TimelineService.get_timeline_projection
        proj = TimelineService.get_timeline_projection(db_session, test_case.id)
        assert len(proj.events) == 2
        for evt in proj.events:
            assert evt.correlation_marker == expected_marker
            assert evt.is_correlated is True
            assert len(evt.findings) == 1
            assert evt.findings[0].id == finding.id

        # 3. Test TimelineService.get_paginated_timeline
        paginated = TimelineService.get_paginated_timeline(db_session, test_case.id, limit=10)
        assert len(paginated.items) == 2
        for evt in paginated.items:
            assert evt.correlation_marker == expected_marker
            assert evt.is_correlated is True
            assert len(evt.findings) == 1
            assert evt.findings[0].id == finding.id

    def test_exclusion_of_rejected_findings(
        self,
        db_session: Session,
        test_case: Case,
        test_evidence: Evidence,
        second_evidence: Evidence,
    ) -> None:
        """Given findings with status REJECTED, they are strictly excluded from correlation."""
        base_time = datetime(2026, 11, 25, 11, 0, 0, tzinfo=UTC)
        obs1 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="dissect",
            source_id=second_evidence.id,
            normalized_content={"cmd": "calc.exe"},
            timestamp_utc=base_time,
        )
        obs2 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            normalized_content={"cmd": "calc.exe"},
            timestamp_utc=base_time + timedelta(seconds=10),
        )
        db_session.add_all([obs1, obs2])

        # Rejected finding
        rejected_finding = Finding(
            id=uuid.uuid4(),
            case_id=test_case.id,
            title="Rejected False Positive",
            severity=FindingSeverity.LOW,
            status=FindingStatus.REJECTED,
            observation_refs=[obs1.id, obs2.id],
        )
        db_session.add(rejected_finding)
        db_session.commit()

        correlator = TimelineCorrelator(db_session)
        corr_resp = correlator.get_case_correlations(test_case.id)
        assert corr_resp.total == 0
        assert corr_resp.correlations == []

        proj = TimelineService.get_timeline_projection(db_session, test_case.id)
        assert len(proj.events) == 2
        for evt in proj.events:
            assert evt.findings == []
            assert evt.correlation_marker is None
            assert evt.correlation_id is None
            assert evt.correlation_markers == []
            assert evt.is_correlated is False

    def test_exclusion_of_proposed_findings(
        self,
        db_session: Session,
        test_case: Case,
        test_evidence: Evidence,
    ) -> None:
        """Given findings with status PROPOSED (unvalidated), they are strictly excluded."""
        base_time = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)
        obs = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            normalized_content={"event_id": 1102},
            timestamp_utc=base_time,
        )
        db_session.add(obs)

        proposed_finding = Finding(
            id=uuid.uuid4(),
            case_id=test_case.id,
            title="Proposed Finding (not reviewed)",
            severity=FindingSeverity.MEDIUM,
            status=FindingStatus.PROPOSED,
            observation_refs=[obs.id],
        )
        db_session.add(proposed_finding)
        db_session.commit()

        proj = TimelineService.get_timeline_projection(db_session, test_case.id)
        assert len(proj.events) == 1
        evt = proj.events[0]
        assert evt.findings == []
        assert evt.correlation_marker is None
        assert evt.is_correlated is False

    def test_observation_without_finding(
        self,
        db_session: Session,
        test_case: Case,
        test_evidence: Evidence,
    ) -> None:
        """Given an observation with no attached finding, it is rendered cleanly."""
        obs = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            normalized_content={"event_id": 4624},
            timestamp_utc=datetime(2026, 11, 25, 13, 0, 0, tzinfo=UTC),
        )
        db_session.add(obs)
        db_session.commit()

        proj = TimelineService.get_timeline_projection(db_session, test_case.id)
        assert len(proj.events) == 1
        evt = proj.events[0]
        assert evt.findings == []
        assert evt.correlation_marker is None
        assert evt.correlation_id is None
        assert evt.correlation_markers == []
        assert evt.is_correlated is False

    def test_multi_tenant_isolation(
        self,
        db_session: Session,
        test_case: Case,
        other_case: Case,
        test_evidence: Evidence,
    ) -> None:
        """Given Case B has findings and observations, Case A sees none of them (Zero Leak)."""
        base_time = datetime(2026, 11, 25, 14, 0, 0, tzinfo=UTC)

        # Evidence and observations in Case B
        ev_b = Evidence(
            id=uuid.uuid4(),
            case_id=other_case.id,
            original_name="OtherSec.evtx",
            file_size=100,
            sha256="b" * 64,
            detected_type="application/x-winevtx",
        )
        db_session.add(ev_b)
        obs_b1 = Observation(
            id=uuid.uuid4(),
            case_id=other_case.id,
            tool_name="python-evtx",
            source_id=ev_b.id,
            normalized_content={"msg": "Case B event 1"},
            timestamp_utc=base_time,
        )
        obs_b2 = Observation(
            id=uuid.uuid4(),
            case_id=other_case.id,
            tool_name="dissect",
            source_id=ev_b.id,
            normalized_content={"msg": "Case B event 2"},
            timestamp_utc=base_time + timedelta(seconds=10),
        )
        db_session.add_all([obs_b1, obs_b2])

        finding_b = Finding(
            id=uuid.uuid4(),
            case_id=other_case.id,
            title="Secret Finding in Case B",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs_b1.id, obs_b2.id],
        )
        db_session.add(finding_b)

        # Observation in Case A
        obs_a = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            normalized_content={"msg": "Case A normal event"},
            timestamp_utc=base_time,
        )
        db_session.add(obs_a)
        db_session.commit()

        # Query Case A correlations and timeline
        corr_a = TimelineService.get_case_correlations(db_session, test_case.id)
        assert corr_a.total == 0
        assert corr_a.correlations == []

        proj_a = TimelineService.get_timeline_projection(db_session, test_case.id)
        assert len(proj_a.events) == 1
        assert proj_a.events[0].observation_id == obs_a.id
        assert proj_a.events[0].findings == []
        assert proj_a.events[0].is_correlated is False

        # Query Case B correlations
        corr_b = TimelineService.get_case_correlations(db_session, other_case.id)
        assert corr_b.total == 1
        assert corr_b.correlations[0].finding_id == finding_b.id

    def test_distinct_sources_same_tool_correlation(
        self,
        db_session: Session,
        test_case: Case,
        test_evidence: Evidence,
        second_evidence: Evidence,
    ) -> None:
        """Given a finding linking observations from the same tool but distinct evidence files,

        then multi-source correlation is recognized (len(sources) >= 2).
        """
        base_time = datetime(2026, 11, 25, 15, 0, 0, tzinfo=UTC)
        obs1 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            normalized_content={"event": 1},
            timestamp_utc=base_time,
        )
        obs2 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=second_evidence.id,  # Distinct source
            normalized_content={"event": 2},
            timestamp_utc=base_time + timedelta(seconds=20),
        )
        db_session.add_all([obs1, obs2])

        finding = Finding(
            id=uuid.uuid4(),
            case_id=test_case.id,
            title="Lateral Movement Across Two Distinct Hosts/Logs",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs1.id, obs2.id],
        )
        db_session.add(finding)
        db_session.commit()

        corr_resp = TimelineService.get_case_correlations(db_session, test_case.id)
        assert corr_resp.total == 1
        group = corr_resp.correlations[0]
        assert group.is_multi_source is True
        assert group.is_multi_tool is False
        assert len(group.sources) == 2

    def test_single_observation_finding_superposition(
        self,
        db_session: Session,
        test_case: Case,
        test_evidence: Evidence,
    ) -> None:
        """Given a validated finding with only 1 observation, finding is superimposed

        but is_correlated is False (cannot correlate a single event alone).
        """
        base_time = datetime(2026, 11, 25, 16, 0, 0, tzinfo=UTC)
        obs = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            normalized_content={"event_id": 7045},
            timestamp_utc=base_time,
        )
        db_session.add(obs)

        finding = Finding(
            id=uuid.uuid4(),
            case_id=test_case.id,
            title="Single Service Installation Fact",
            severity=FindingSeverity.MEDIUM,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs.id],
        )
        db_session.add(finding)
        db_session.commit()

        proj = TimelineService.get_timeline_projection(db_session, test_case.id)
        assert len(proj.events) == 1
        evt = proj.events[0]
        assert len(evt.findings) == 1
        assert evt.findings[0].id == finding.id
        assert evt.findings[0].title == finding.title
        assert evt.is_correlated is False
        assert evt.correlation_marker is None

        # Not included in multi-source correlation groups
        corr_resp = TimelineService.get_case_correlations(db_session, test_case.id)
        assert corr_resp.total == 0

    def test_invariant_2_pure_in_memory_projection(
        self,
        db_session: Session,
        test_case: Case,
        test_evidence: Evidence,
        second_evidence: Evidence,
    ) -> None:
        """Verify strict Invariant 2: correlation never inserts, alters, or drops records."""
        base_time = datetime(2026, 11, 25, 17, 0, 0, tzinfo=UTC)
        obs1 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="dissect",
            source_id=second_evidence.id,
            normalized_content={"app": "test.exe"},
            timestamp_utc=base_time,
        )
        obs2 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            normalized_content={"event_id": 4688},
            timestamp_utc=base_time + timedelta(seconds=5),
        )
        db_session.add_all([obs1, obs2])
        finding = Finding(
            id=uuid.uuid4(),
            case_id=test_case.id,
            title="Correlated execution",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs1.id, obs2.id],
        )
        db_session.add(finding)
        db_session.commit()

        obs_count_before = db_session.scalar(select(func.count(Observation.id)))
        finding_count_before = db_session.scalar(select(func.count(Finding.id)))

        # Invoke all projection and correlation methods
        TimelineService.get_timeline_projection(db_session, test_case.id)
        TimelineService.get_paginated_timeline(db_session, test_case.id)
        TimelineService.get_case_correlations(db_session, test_case.id)

        obs_count_after = db_session.scalar(select(func.count(Observation.id)))
        finding_count_after = db_session.scalar(select(func.count(Finding.id)))

        assert obs_count_before == obs_count_after
        assert finding_count_before == finding_count_after

    def test_paginated_timeline_filtering_by_correlation(
        self,
        db_session: Session,
        test_case: Case,
        test_evidence: Evidence,
        second_evidence: Evidence,
    ) -> None:
        """Test paginated timeline filtering by correlation attributes."""
        base_time = datetime(2026, 11, 25, 18, 0, 0, tzinfo=UTC)

        # Correlated pair
        obs1 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="dissect",
            source_id=second_evidence.id,
            normalized_content={"msg": "correlated 1"},
            timestamp_utc=base_time,
        )
        obs2 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            normalized_content={"msg": "correlated 2"},
            timestamp_utc=base_time + timedelta(minutes=1),
        )
        # Uncorrelated observation
        obs3 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            normalized_content={"msg": "independent event"},
            timestamp_utc=base_time + timedelta(minutes=2),
        )
        db_session.add_all([obs1, obs2, obs3])

        finding = Finding(
            id=uuid.uuid4(),
            case_id=test_case.id,
            title="Correlated finding",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs1.id, obs2.id],
        )
        db_session.add(finding)
        db_session.commit()

        # 1. Filter is_correlated=True
        resp_corr = TimelineService.get_paginated_timeline(
            db_session, test_case.id, is_correlated=True
        )
        assert resp_corr.total == 2
        assert {e.observation_id for e in resp_corr.items} == {obs1.id, obs2.id}

        # 2. Filter is_correlated=False
        resp_uncorr = TimelineService.get_paginated_timeline(
            db_session, test_case.id, is_correlated=False
        )
        assert resp_uncorr.total == 1
        assert resp_uncorr.items[0].observation_id == obs3.id

        # 3. Filter by correlation_marker
        marker = f"corr-{finding.id}"
        resp_marker = TimelineService.get_paginated_timeline(
            db_session, test_case.id, correlation_marker=marker
        )
        assert resp_marker.total == 2
        assert all(e.correlation_marker == marker for e in resp_marker.items)

        # 4. Filter by finding_id
        resp_fid = TimelineService.get_paginated_timeline(
            db_session, test_case.id, finding_id=finding.id
        )
        assert resp_fid.total == 2
        assert {e.observation_id for e in resp_fid.items} == {obs1.id, obs2.id}

    def test_undated_observation_in_correlation_group(
        self,
        db_session: Session,
        test_case: Case,
        test_evidence: Evidence,
        second_evidence: Evidence,
    ) -> None:
        """Undated observations appear in undated_events with total_undated populated."""
        base_time = datetime(2026, 11, 25, 19, 0, 0, tzinfo=UTC)
        obs_dated = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="dissect",
            source_id=second_evidence.id,
            normalized_content={"app": "test.exe"},
            timestamp_utc=base_time,
        )
        obs_undated = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            normalized_content={"description": "Undated policy finding"},
            timestamp_utc=None,
        )
        db_session.add_all([obs_dated, obs_undated])

        finding = Finding(
            id=uuid.uuid4(),
            case_id=test_case.id,
            title="Mixed dated/undated correlation",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs_dated.id, obs_undated.id],
        )
        db_session.add(finding)
        db_session.commit()

        correlator = TimelineCorrelator(db_session)
        corr_resp = correlator.get_case_correlations(test_case.id)
        assert corr_resp.total == 1
        group = corr_resp.correlations[0]
        assert group.total_events == 1
        assert len(group.events) == 1
        assert group.total_undated == 1
        assert len(group.undated_events) == 1
        assert group.undated_events[0].observation_id == obs_undated.id
        assert group.undated_events[0].findings[0].id == finding.id
        assert group.undated_events[0].is_correlated is True
        assert group.undated_events[0].correlation_marker == f"corr-{finding.id}"

    def test_observation_linked_to_multiple_validated_findings(
        self,
        db_session: Session,
        test_case: Case,
        test_evidence: Evidence,
        second_evidence: Evidence,
    ) -> None:
        """Observation referenced by multiple validated findings receives all references."""
        base_time = datetime(2026, 11, 25, 20, 0, 0, tzinfo=UTC)
        obs1 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="dissect",
            source_id=second_evidence.id,
            normalized_content={"proc": "powershell.exe"},
            timestamp_utc=base_time,
        )
        obs2 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            normalized_content={"event_id": 4104},
            timestamp_utc=base_time + timedelta(seconds=10),
        )
        obs3 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="parse_registry",
            source_id=test_evidence.id,
            normalized_content={"key": "Run"},
            timestamp_utc=base_time + timedelta(seconds=20),
        )
        db_session.add_all([obs1, obs2, obs3])

        finding_a = Finding(
            id=uuid.uuid4(),
            case_id=test_case.id,
            title="Finding A: Script Execution",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs1.id, obs2.id],
        )
        finding_b = Finding(
            id=uuid.uuid4(),
            case_id=test_case.id,
            title="Finding B: Persistence via Script",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs2.id, obs3.id],
        )
        db_session.add_all([finding_a, finding_b])
        db_session.commit()

        proj = TimelineService.get_timeline_projection(db_session, test_case.id)
        evt2 = next(e for e in proj.events if e.observation_id == obs2.id)
        assert len(evt2.findings) == 2
        finding_ids = {f.id for f in evt2.findings}
        assert finding_ids == {finding_a.id, finding_b.id}
        assert f"corr-{finding_a.id}" in evt2.correlation_markers
        assert f"corr-{finding_b.id}" in evt2.correlation_markers
        assert evt2.is_correlated is True

    def test_distinct_tools_same_evidence_file_correlation(
        self,
        db_session: Session,
        test_case: Case,
        test_evidence: Evidence,
    ) -> None:
        """Distinct tools on the same evidence file: is_multi_tool=True, is_multi_source=False."""
        base_time = datetime(2026, 11, 25, 21, 0, 0, tzinfo=UTC)
        obs1 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="dissect",
            source_id=test_evidence.id,
            normalized_content={"msg": "prefetch from img"},
            timestamp_utc=base_time,
        )
        obs2 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,  # Same evidence file
            normalized_content={"msg": "evtx from img"},
            timestamp_utc=base_time + timedelta(seconds=15),
        )
        db_session.add_all([obs1, obs2])

        finding = Finding(
            id=uuid.uuid4(),
            case_id=test_case.id,
            title="Multi-tool on same evidence",
            severity=FindingSeverity.MEDIUM,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs1.id, obs2.id],
        )
        db_session.add(finding)
        db_session.commit()

        corr_resp = TimelineService.get_case_correlations(db_session, test_case.id)
        assert corr_resp.total == 1
        group = corr_resp.correlations[0]
        assert group.is_multi_tool is True
        assert group.is_multi_source is False
        assert len(group.tools) == 2
        assert len(group.sources) == 1

        proj = TimelineService.get_timeline_projection(db_session, test_case.id)
        for e in proj.events:
            assert e.is_correlated is True
            assert e.correlation_marker == f"corr-{finding.id}"

    def test_filtering_by_correlation_marker_on_single_source_returns_empty(
        self,
        db_session: Session,
        test_case: Case,
        test_evidence: Evidence,
    ) -> None:
        """Filtering by correlation_marker on a single-source finding returns 0 events."""
        base_time = datetime(2026, 11, 25, 22, 0, 0, tzinfo=UTC)
        obs = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="python-evtx",
            source_id=test_evidence.id,
            normalized_content={"msg": "single event"},
            timestamp_utc=base_time,
        )
        db_session.add(obs)

        # Single-source finding
        finding = Finding(
            id=uuid.uuid4(),
            case_id=test_case.id,
            title="Single-source finding",
            severity=FindingSeverity.LOW,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs.id],
        )
        db_session.add(finding)
        db_session.commit()

        marker = f"corr-{finding.id}"
        resp = TimelineService.get_paginated_timeline(
            db_session, test_case.id, correlation_marker=marker
        )
        assert resp.total == 0
        assert resp.items == []
