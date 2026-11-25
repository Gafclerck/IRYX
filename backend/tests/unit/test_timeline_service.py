"""Unit tests for TimelineService chronological projection (Story 7.1, FR24, Invariant 2)."""

import uuid
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from iryx.analytics import (
    Observation,
    TimelineListResponse,
    TimelineProjectionResponse,
    TimelineService,
    UndatedFactOut,
    extract_technical_summary,
)
from iryx.auth.models import Organization, User
from iryx.cases.models import Case
from iryx.db.base import Base
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
    """Create a test case for timeline testing."""
    case = Case(
        id=uuid.uuid4(),
        organization_id=test_organization.id,
        title="DFIR Unified Timeline Test Case",
        description="Case for testing chronological correlation",
        created_by=test_user.id,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


@pytest.fixture
def test_evidence(db_session: Session, test_case: Case) -> Evidence:
    """Create a sealed digital evidence attached to the test case."""
    evidence = Evidence(
        id=uuid.uuid4(),
        case_id=test_case.id,
        original_name="Security_20261125.evtx",
        file_size=1024 * 1024,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        detected_type="application/x-winevtx",
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)
    return evidence


class TestTimelineServiceNominal:
    """Nominal tests for TimelineService multi-source chronological reconstruction."""

    def test_empty_case_timeline_projection(self, db_session: Session, test_case: Case) -> None:
        """Given a case without observations, then timeline returns empty lists with zero totals."""
        response = TimelineService.get_timeline_projection(db_session, test_case.id)

        assert isinstance(response, TimelineProjectionResponse)
        assert response.case_id == test_case.id
        assert response.events == []
        assert response.undated_events == []
        assert response.total_events == 0
        assert response.total_undated == 0

    def test_nominal_multi_sources_chronological_ordering_utc(
        self, db_session: Session, test_case: Case, test_evidence: Evidence
    ) -> None:
        """Given observations with timestamps, events are ordered in strictly ascending UTC."""
        evidence2 = Evidence(
            id=uuid.uuid4(),
            case_id=test_case.id,
            original_name="SYSTEM.hive",
            file_size=512 * 1024,
            sha256="a" * 64,
            detected_type="application/x-registry-hive",
        )
        db_session.add(evidence2)
        db_session.commit()

        base_time = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
        evtx_tool_exec_id = uuid.uuid4()

        obs_evtx = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            source_id=test_evidence.id,
            tool_name="parse_evtx",
            tool_execution_id=evtx_tool_exec_id,
            normalized_content={
                "event_id": 4624,
                "message": "Successful logon (Administrator)",
            },
            timestamp_utc=base_time + timedelta(minutes=15),
            source_location="Security.evtx:Record102",
        )
        obs_registry = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            source_id=evidence2.id,
            tool_name="parse_registry",
            normalized_content={
                "key_path": r"HKLM\SYSTEM\CurrentControlSet\Services",
                "summary": "Persistence service installed",
            },
            timestamp_utc=base_time + timedelta(minutes=5),
            source_location="SYSTEM:Services/BadService",
        )
        obs_prefetch = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            source_id=None,
            tool_name="parse_execution",
            normalized_content={
                "executable_name": "MIMIKATZ.EXE",
                "command_line": "mimikatz.exe sekurlsa::logonpasswords",
            },
            timestamp_utc=base_time + timedelta(minutes=30),
            source_location=r"C:\Windows\Prefetch\MIMIKATZ.EXE-ABCD.pf",
        )
        obs_volatility = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            source_id=None,
            tool_name="analyze_memory",
            normalized_content={
                "plugin": "windows.netscan",
                "description": "Suspicious C2 network socket to 198.51.100.4:443",
            },
            timestamp_utc=base_time,  # earliest event
            source_location="MemoryDump:netscan_offset_0x4000",
        )

        db_session.add_all([obs_evtx, obs_registry, obs_prefetch, obs_volatility])
        db_session.commit()

        response = TimelineService.get_timeline_projection(db_session, test_case.id)

        assert response.total_events == 4
        assert response.total_undated == 0
        assert len(response.events) == 4

        # Verify strict ascending order
        timestamps = [e.timestamp_utc for e in response.events]
        assert timestamps == sorted(timestamps)

        # Event 0: Volatility
        assert response.events[0].tool_name == "analyze_memory"
        assert response.events[0].summary == "Suspicious C2 network socket to 198.51.100.4:443"
        assert response.events[0].evidence_id is None
        assert response.events[0].evidence_name is None
        assert response.events[0].source_location == "MemoryDump:netscan_offset_0x4000"
        assert response.events[0].details == {
            "plugin": "windows.netscan",
            "description": "Suspicious C2 network socket to 198.51.100.4:443",
        }
        assert response.events[0].tool_execution_id is None

        # Event 1: Registry
        assert response.events[1].tool_name == "parse_registry"
        assert response.events[1].evidence_id == evidence2.id
        assert response.events[1].evidence_name == "SYSTEM.hive"
        assert response.events[1].summary == "Persistence service installed"
        assert response.events[1].source_location == "SYSTEM:Services/BadService"
        assert response.events[1].details == {
            "key_path": r"HKLM\SYSTEM\CurrentControlSet\Services",
            "summary": "Persistence service installed",
        }

        # Event 2: EVTX
        assert response.events[2].tool_name == "parse_evtx"
        assert response.events[2].evidence_id == test_evidence.id
        assert response.events[2].evidence_name == "Security_20261125.evtx"
        assert response.events[2].summary == "Successful logon (Administrator)"
        assert response.events[2].source_location == "Security.evtx:Record102"
        assert response.events[2].details == {
            "event_id": 4624,
            "message": "Successful logon (Administrator)",
        }
        assert response.events[2].tool_execution_id == evtx_tool_exec_id

        # Event 3: Prefetch
        assert response.events[3].tool_name == "parse_execution"
        assert response.events[3].summary == "mimikatz.exe sekurlsa::logonpasswords"
        assert response.events[3].source_location == r"C:\Windows\Prefetch\MIMIKATZ.EXE-ABCD.pf"
        assert response.events[3].details == {
            "executable_name": "MIMIKATZ.EXE",
            "command_line": "mimikatz.exe sekurlsa::logonpasswords",
        }

    def test_tie_breaking_deterministic_order(self, db_session: Session, test_case: Case) -> None:
        """Observations with identical timestamp_utc tie-break deterministically by ID."""
        common_time = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)

        id1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
        id2 = uuid.UUID("22222222-2222-2222-2222-222222222222")
        id3 = uuid.UUID("33333333-3333-3333-3333-333333333333")

        obs3 = Observation(
            id=id3,
            case_id=test_case.id,
            tool_name="tool_c",
            normalized_content={"summary": "Fact 3"},
            timestamp_utc=common_time,
        )
        obs1 = Observation(
            id=id1,
            case_id=test_case.id,
            tool_name="tool_a",
            normalized_content={"summary": "Fact 1"},
            timestamp_utc=common_time,
        )
        obs2 = Observation(
            id=id2,
            case_id=test_case.id,
            tool_name="tool_b",
            normalized_content={"summary": "Fact 2"},
            timestamp_utc=common_time,
        )

        db_session.add_all([obs3, obs1, obs2])
        db_session.commit()

        response = TimelineService.get_timeline_projection(db_session, test_case.id)

        assert len(response.events) == 3
        assert [e.observation_id for e in response.events] == [id1, id2, id3]


class TestUndatedFactsAndPartitioning:
    """Tests isolating undated observations in undated_events (FR24)."""

    def test_pure_undated_events(self, db_session: Session, test_case: Case) -> None:
        """Given observations without timestamps, then partitioned into undated_events."""
        tool_exec_id = uuid.uuid4()
        obs_undated_1 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="hash_sha256",
            tool_execution_id=tool_exec_id,
            normalized_content={
                "summary": "Calculated SHA-256 integrity hash",
                "sha256": "abc123def456",
            },
            timestamp_utc=None,
            source_location="evidence_file.raw",
        )
        obs_undated_2 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="custom_scanner",
            normalized_content={"message": "Static signature match detected"},
            timestamp_utc=None,
        )
        db_session.add_all([obs_undated_1, obs_undated_2])
        db_session.commit()

        response = TimelineService.get_timeline_projection(db_session, test_case.id)

        assert response.total_events == 0
        assert response.total_undated == 2
        assert len(response.events) == 0
        assert len(response.undated_events) == 2

        undated_ids = {u.observation_id for u in response.undated_events}
        assert obs_undated_1.id in undated_ids
        assert obs_undated_2.id in undated_ids

        fact1 = next(u for u in response.undated_events if u.observation_id == obs_undated_1.id)
        assert isinstance(fact1, UndatedFactOut)
        assert fact1.timestamp_utc is None
        assert fact1.source_location == "evidence_file.raw"
        assert fact1.tool_execution_id == tool_exec_id
        assert fact1.details == {
            "summary": "Calculated SHA-256 integrity hash",
            "sha256": "abc123def456",
        }

    def test_mixed_dated_and_undated_partitioning(
        self, db_session: Session, test_case: Case, test_evidence: Evidence
    ) -> None:
        """Given a mix of dated and undated observations, both are correctly partitioned."""
        dt1 = datetime(2026, 11, 25, 8, 30, 0, tzinfo=UTC)
        dt2 = datetime(2026, 11, 25, 9, 0, 0, tzinfo=UTC)

        obs_dated_1 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            source_id=test_evidence.id,
            tool_name="parse_evtx",
            normalized_content={"summary": "Event 1"},
            timestamp_utc=dt1,
        )
        obs_undated = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            source_id=test_evidence.id,
            tool_name="hash_sha256",
            normalized_content={"summary": "Hash check"},
            timestamp_utc=None,
        )
        obs_dated_2 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            source_id=test_evidence.id,
            tool_name="parse_evtx",
            normalized_content={"summary": "Event 2"},
            timestamp_utc=dt2,
        )

        db_session.add_all([obs_dated_1, obs_undated, obs_dated_2])
        db_session.commit()

        response = TimelineService.get_timeline_projection(db_session, test_case.id)

        assert response.total_events == 2
        assert response.total_undated == 1
        assert len(response.events) == 2
        assert len(response.undated_events) == 1

        assert response.events[0].observation_id == obs_dated_1.id
        assert response.events[1].observation_id == obs_dated_2.id
        assert response.undated_events[0].observation_id == obs_undated.id
        assert response.undated_events[0].evidence_name == "Security_20261125.evtx"

    def test_undated_fact_out_rejects_non_null_timestamp(self) -> None:
        """UndatedFactOut must reject any non-null timestamp_utc."""
        with pytest.raises(ValueError, match="UndatedFactOut must have timestamp_utc set to None"):
            UndatedFactOut(
                observation_id=uuid.uuid4(),
                tool_name="test_tool",
                summary="test summary",
                timestamp_utc=datetime.now(UTC),
            )


class TestMultiTenantIsolation:
    """Tests ensuring strict multi-tenant boundary by case_id."""

    def test_multi_tenant_isolation_between_cases(
        self, db_session: Session, test_organization: Organization, test_user: User
    ) -> None:
        """Given observations in Case A and B, Case A projection has 0 events from Case B."""
        case_a = Case(
            id=uuid.uuid4(),
            organization_id=test_organization.id,
            title="Case A",
            description="Desc A",
            created_by=test_user.id,
        )
        case_b = Case(
            id=uuid.uuid4(),
            organization_id=test_organization.id,
            title="Case B",
            description="Desc B",
            created_by=test_user.id,
        )
        db_session.add_all([case_a, case_b])
        db_session.commit()

        now = datetime.now(UTC)
        obs_a = Observation(
            id=uuid.uuid4(),
            case_id=case_a.id,
            tool_name="tool_a",
            normalized_content={"summary": "Fact Case A"},
            timestamp_utc=now,
        )
        obs_b = Observation(
            id=uuid.uuid4(),
            case_id=case_b.id,
            tool_name="tool_b",
            normalized_content={"summary": "Fact Case B"},
            timestamp_utc=now,
        )
        db_session.add_all([obs_a, obs_b])
        db_session.commit()

        res_a = TimelineService.get_timeline_projection(db_session, case_a.id)
        res_b = TimelineService.get_timeline_projection(db_session, case_b.id)

        assert res_a.total_events == 1
        assert res_a.events[0].observation_id == obs_a.id

        assert res_b.total_events == 1
        assert res_b.events[0].observation_id == obs_b.id


class TestTimezoneHandling:
    """Tests guaranteeing timezone-aware UTC standardization."""

    def test_naive_datetime_normalized_to_utc(self, db_session: Session, test_case: Case) -> None:
        """Given observation with naive datetime, safely normalized to timezone-aware UTC."""
        naive_dt = datetime(2026, 11, 25, 14, 30, 0)
        obs = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="parse_text_logs",
            normalized_content={"summary": "Log entry"},
            timestamp_utc=naive_dt,
        )
        # Directly assert UTC normalization on the Observation instance
        assert obs.timestamp_utc is not None
        assert obs.timestamp_utc.tzinfo == UTC

        db_session.add(obs)
        db_session.commit()

        response = TimelineService.get_timeline_projection(db_session, test_case.id)
        assert len(response.events) == 1
        event = response.events[0]
        assert event.timestamp_utc.tzinfo is not None
        assert event.timestamp_utc.utcoffset() == timedelta(0)

    def test_offset_datetime_converted_to_utc(self, db_session: Session, test_case: Case) -> None:
        """Given an observation with non-UTC offset (UTC+2), it is converted to exact UTC."""
        tz_plus_2 = timezone(timedelta(hours=2))
        dt_plus_2 = datetime(2026, 11, 25, 16, 0, 0, tzinfo=tz_plus_2)

        obs = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="parse_evtx",
            normalized_content={"summary": "Offset test"},
            timestamp_utc=dt_plus_2,
        )
        # Directly assert UTC conversion on the Observation instance
        assert obs.timestamp_utc is not None
        assert obs.timestamp_utc.tzinfo == UTC
        assert obs.timestamp_utc.hour == 14

        db_session.add(obs)
        db_session.commit()

        response = TimelineService.get_timeline_projection(db_session, test_case.id)
        assert len(response.events) == 1
        event = response.events[0]
        assert event.timestamp_utc.hour == 14
        assert event.timestamp_utc.tzinfo == UTC


class TestTechnicalSummaryExtraction:
    """Tests verifying robust extraction of technical summary without exception."""

    def test_priority_keys_extraction(self) -> None:
        """Verify summary, message, description, event_description, command_line in priority."""
        assert (
            extract_technical_summary(
                {"summary": "High-level summary", "message": "Ignored message"}
            )
            == "High-level summary"
        )
        assert (
            extract_technical_summary({"message": "Message content", "description": "Ignored"})
            == "Message content"
        )
        assert (
            extract_technical_summary({"description": "Description content"})
            == "Description content"
        )
        assert extract_technical_summary({"event_description": "Event desc"}) == "Event desc"
        assert (
            extract_technical_summary({"command_line": "powershell.exe -enc AAAA"})
            == "powershell.exe -enc AAAA"
        )

    def test_domain_field_fallbacks(self) -> None:
        """Verify DFIR domain fallbacks (event_id, process_name, registry key, raw)."""
        assert (
            extract_technical_summary({"event_id": 4688, "channel": "Security"})
            == "Event 4688 (Security)"
        )
        assert extract_technical_summary({"EventID": 7045}) == "Event 7045"
        # Test event_id = 0
        assert (
            extract_technical_summary({"event_id": 0, "channel": "Security"})
            == "Event 0 (Security)"
        )
        assert extract_technical_summary({"event_id": 0}) == "Event 0"

        assert (
            extract_technical_summary({"process_name": "svchost.exe", "pid": 1044})
            == "Process svchost.exe (PID 1044)"
        )
        # Test pid = 0
        assert (
            extract_technical_summary({"process_name": "System", "pid": 0})
            == "Process System (PID 0)"
        )

        assert extract_technical_summary({"executable_name": "cmd.exe"}) == "Process cmd.exe"
        assert (
            extract_technical_summary({"key_path": r"HKLM\SOFTWARE\Run"})
            == r"Registry: HKLM\SOFTWARE\Run"
        )
        assert (
            extract_technical_summary({"raw": "192.168.1.1 GET /admin 200"})
            == "192.168.1.1 GET /admin 200"
        )
        # Test whitespace command falls through
        assert extract_technical_summary({"command": "   "}) == "Observation fact"

    def test_unstructured_and_edge_case_fallbacks(self) -> None:
        """Verify fallback on empty, non-dict or unstructured data without raising exceptions."""
        assert extract_technical_summary(None) == "Observation fact"
        assert extract_technical_summary({}) == "Observation fact"
        assert extract_technical_summary("") == "Observation fact"
        assert extract_technical_summary("  Raw text summary  ") == "Raw text summary"
        assert extract_technical_summary(12345) == "12345"
        assert (
            extract_technical_summary({"custom_field": "val1", "status": "ok"})
            == "custom_field=val1, status=ok"
        )


class TestInvariant2Compliance:
    """Tests validating strict compliance with Invariant 2 (pure read-only projection)."""

    def test_no_mutation_methods_exist_on_timeline_service(self) -> None:
        """Verify TimelineService does not expose methods to forge, create, or update events."""
        forbidden_method_prefixes = (
            "create_",
            "add_",
            "insert_",
            "update_",
            "delete_",
            "modify_",
            "forge_",
        )
        for attr in dir(TimelineService):
            for prefix in forbidden_method_prefixes:
                assert not attr.startswith(prefix), (
                    f"Forbidden mutation method found on TimelineService: {attr}"
                )

    def test_no_mutable_timeline_table_exists(self) -> None:
        """Verify that no mutable table such as 'timeline_events' exists in ORM metadata."""
        table_names = list(Base.metadata.tables.keys())
        assert "timeline_events" not in table_names
        assert "timeline" not in table_names

    def test_timeline_projection_is_pure_and_idempotent(
        self, db_session: Session, test_case: Case
    ) -> None:
        """Verify that invoking projection twice yields identical output with zero DB mutation."""
        obs = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="parse_evtx",
            normalized_content={"summary": "Event 1"},
            timestamp_utc=datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC),
        )
        db_session.add(obs)
        db_session.commit()

        count_before = db_session.query(Observation).count()

        res1 = TimelineService.get_timeline_projection(db_session, test_case.id)
        res2 = TimelineService.get_timeline_projection(db_session, test_case.id)

        count_after = db_session.query(Observation).count()

        assert count_before == count_after == 1
        assert res1.total_events == res2.total_events == 1
        assert res1.events[0].observation_id == res2.events[0].observation_id


class TestCallingConventionsAndEdgeCases:
    """Tests confirming versatile calling conventions and edge case resilience."""

    def test_class_call_positional(self, db_session: Session, test_case: Case) -> None:
        res = TimelineService.get_timeline_projection(db_session, test_case.id)
        assert isinstance(res, TimelineProjectionResponse)

    def test_class_call_kwargs(self, db_session: Session, test_case: Case) -> None:
        res = TimelineService.get_timeline_projection(db=db_session, case_id=test_case.id)
        assert isinstance(res, TimelineProjectionResponse)

    def test_instance_call_with_bound_db(self, db_session: Session, test_case: Case) -> None:
        service = TimelineService(db_session)
        res = service.get_timeline_projection(test_case.id)
        assert isinstance(res, TimelineProjectionResponse)

    def test_instance_call_with_kwargs(self, db_session: Session, test_case: Case) -> None:
        service = TimelineService(db_session)
        res = service.get_timeline_projection(case_id=test_case.id)
        assert isinstance(res, TimelineProjectionResponse)

    def test_string_case_id_handling(self, db_session: Session, test_case: Case) -> None:
        """Verify that string case_id is safely parsed and accepted."""
        res = TimelineService.get_timeline_projection(db_session, str(test_case.id))
        assert res.case_id == test_case.id

    def test_invalid_string_case_id_raises_value_error(self, db_session: Session) -> None:
        """Verify that invalid case_id string raises a descriptive ValueError."""
        with pytest.raises(ValueError, match="Invalid case_id format"):
            TimelineService.get_timeline_projection(db_session, "not-a-valid-uuid")

    def test_missing_db_or_case_id_raises_value_error(self, db_session: Session) -> None:
        with pytest.raises(ValueError, match="Database session"):
            TimelineService.get_timeline_projection(None, uuid.uuid4())  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="Case ID"):
            service = TimelineService(db_session)
            service.get_timeline_projection(case_id=None)  # type: ignore[arg-type]

    def test_timeline_projection_response_populate_totals_with_none(self) -> None:
        """TimelineProjectionResponse recalculates totals when explicitly passed as None."""
        resp = TimelineProjectionResponse(
            events=[],
            undated_events=[],
            total_events=None,
            total_undated=None,
        )
        assert resp.total_events == 0
        assert resp.total_undated == 0

    def test_malformed_string_timestamp_graceful_fallback(
        self, db_session: Session, test_case: Case
    ) -> None:
        """Observation with malformed string timestamp falls back gracefully to undated."""
        obs = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="tool_bad_date",
            normalized_content={"summary": "Corrupted date entry"},
        )
        obs.timestamp_utc = "not-a-date"  # type: ignore[assignment]
        with patch.object(db_session, "execute") as mock_exec:
            mock_exec.return_value.all.return_value = [(obs, "evidence.raw")]
            resp = TimelineService.get_timeline_projection(db_session, test_case.id)

        assert resp.total_events == 0
        assert resp.total_undated == 1
        assert resp.undated_events[0].observation_id == obs.id

    def test_non_dict_normalized_content_wrapped_in_raw(
        self, db_session: Session, test_case: Case
    ) -> None:
        """Non-dict normalized_content is wrapped in {'raw': ...} without dropping."""
        obs = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            tool_name="tool_list",
            timestamp_utc=datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC),
        )
        obs.normalized_content = ["record1", "record2"]  # type: ignore[assignment]
        db_session.add(obs)
        db_session.commit()

        resp = TimelineService.get_timeline_projection(db_session, test_case.id)
        assert len(resp.events) == 1
        assert resp.events[0].details == {"raw": ["record1", "record2"]}


class TestTimelineServicePaginated:
    """Unit tests for TimelineService.get_paginated_timeline (Story 7.2, NFR-PERF-07)."""

    def test_paginated_timeline_instance_and_class_dispatch(
        self, db_session: Session, test_case: Case, test_evidence: Evidence
    ) -> None:
        """Verify both instance and class dispatch work identically for get_paginated_timeline."""
        obs = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            source_id=test_evidence.id,
            tool_name="test_tool",
            normalized_content={"msg": "dispatch test"},
            timestamp_utc=datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC),
        )
        db_session.add(obs)
        db_session.commit()

        # Class call: TimelineService.get_paginated_timeline(db, case_id)
        resp_class = TimelineService.get_paginated_timeline(db_session, test_case.id)
        assert isinstance(resp_class, TimelineListResponse)
        assert resp_class.total == 1
        assert len(resp_class.items) == 1
        assert resp_class.items[0].observation_id == obs.id

        # Instance call: TimelineService(db).get_paginated_timeline(case_id)
        service = TimelineService(db_session)
        resp_inst = service.get_paginated_timeline(test_case.id)
        assert isinstance(resp_inst, TimelineListResponse)
        assert resp_inst.total == 1
        assert len(resp_inst.items) == 1
        assert resp_inst.items[0].observation_id == obs.id

    def test_paginated_timeline_positional_arguments_dispatch(
        self, db_session: Session, test_case: Case
    ) -> None:
        """Verify positional arguments (case_id, limit, offset) are honored in dispatcher."""
        base_time = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
        for i in range(15):
            db_session.add(
                Observation(
                    id=uuid.uuid4(),
                    case_id=test_case.id,
                    tool_name="test_tool",
                    normalized_content={"idx": i},
                    timestamp_utc=base_time + timedelta(minutes=i),
                )
            )
        db_session.commit()

        service = TimelineService(db_session)
        # Call with positional args: case_id, limit=5, offset=10
        resp = service.get_paginated_timeline(test_case.id, 5, 10)
        assert resp.total == 15
        assert resp.limit == 5
        assert resp.offset == 10
        assert len(resp.items) == 5
        assert resp.has_more is False

    def test_paginated_timeline_keyword_arguments_dispatch(
        self, db_session: Session, test_case: Case, test_evidence: Evidence
    ) -> None:
        """Verify keyword arguments are properly accepted and filtered."""
        base_time = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
        obs1 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            source_id=test_evidence.id,
            tool_name="python-evtx",
            normalized_content={"msg": "evtx"},
            timestamp_utc=base_time,
        )
        obs2 = Observation(
            id=uuid.uuid4(),
            case_id=test_case.id,
            source_id=None,
            tool_name="volatility",
            normalized_content={"msg": "volatility"},
            timestamp_utc=base_time + timedelta(minutes=5),
        )
        db_session.add_all([obs1, obs2])
        db_session.commit()

        service = TimelineService(db_session)
        resp = service.get_paginated_timeline(
            case_id=test_case.id,
            limit=10,
            offset=0,
            tool_name="python-evtx",
            evidence_id=test_evidence.id,
        )
        assert resp.total == 1
        assert len(resp.items) == 1
        assert resp.items[0].observation_id == obs1.id

    def test_paginated_timeline_non_utc_timezone_conversion(
        self, db_session: Session, test_case: Case
    ) -> None:
        """Verify timezone-aware non-UTC datetimes are correctly converted to UTC for filtering."""
        # 12:00 UTC
        obs_utc = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)
        db_session.add(
            Observation(
                id=uuid.uuid4(),
                case_id=test_case.id,
                tool_name="test_tz",
                normalized_content={"msg": "noon utc"},
                timestamp_utc=obs_utc,
            )
        )
        db_session.commit()

        # 14:00 in UTC+2 is 12:00 UTC (exact match)
        tz_plus_2 = timezone(timedelta(hours=2))
        start_tz = datetime(2026, 11, 25, 13, 0, 0, tzinfo=tz_plus_2)  # 11:00 UTC
        end_tz = datetime(2026, 11, 25, 15, 0, 0, tzinfo=tz_plus_2)  # 13:00 UTC

        resp = TimelineService.get_paginated_timeline(
            db=db_session,
            case_id=test_case.id,
            start_time=start_tz,
            end_time=end_tz,
        )
        assert resp.total == 1
        assert len(resp.items) == 1
        assert resp.items[0].timestamp_utc == obs_utc

    def test_paginated_timeline_empty_tool_name_treated_as_none(
        self, db_session: Session, test_case: Case
    ) -> None:
        """Verify empty and whitespace tool_name strings are sanitized and return all events."""
        base_time = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
        db_session.add(
            Observation(
                id=uuid.uuid4(),
                case_id=test_case.id,
                tool_name="tool_a",
                normalized_content={"msg": "a"},
                timestamp_utc=base_time,
            )
        )
        db_session.add(
            Observation(
                id=uuid.uuid4(),
                case_id=test_case.id,
                tool_name="tool_b",
                normalized_content={"msg": "b"},
                timestamp_utc=base_time + timedelta(minutes=1),
            )
        )
        db_session.commit()

        service = TimelineService(db_session)
        resp_empty = service.get_paginated_timeline(test_case.id, tool_name="")
        assert resp_empty.total == 2

        resp_whitespace = service.get_paginated_timeline(test_case.id, tool_name="   ")
        assert resp_whitespace.total == 2

    def test_paginated_timeline_deterministic_tie_breaking(
        self, db_session: Session, test_case: Case
    ) -> None:
        """Verify identical timestamps are sorted deterministically by observation id ASC."""
        same_time = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
        id1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
        id2 = uuid.UUID("00000000-0000-0000-0000-000000000002")
        id3 = uuid.UUID("00000000-0000-0000-0000-000000000003")

        # Add in reverse id order
        for oid in [id3, id1, id2]:
            db_session.add(
                Observation(
                    id=oid,
                    case_id=test_case.id,
                    tool_name="tie_tool",
                    normalized_content={"id": str(oid)},
                    timestamp_utc=same_time,
                )
            )
        db_session.commit()

        service = TimelineService(db_session)
        resp = service.get_paginated_timeline(test_case.id)
        assert resp.total == 3
        returned_ids = [item.observation_id for item in resp.items]
        assert returned_ids == [id1, id2, id3]

    def test_paginated_timeline_early_exit_on_empty_or_offset_exceeded(
        self, db_session: Session, test_case: Case
    ) -> None:
        """Verify early exit when total == 0 or offset >= total returns empty response."""
        # Empty case
        service = TimelineService(db_session)
        resp_empty = service.get_paginated_timeline(test_case.id)
        assert resp_empty.total == 0
        assert resp_empty.items == []
        assert resp_empty.has_more is False

        # Populate 2 items
        base_time = datetime(2026, 11, 25, 10, 0, 0, tzinfo=UTC)
        db_session.add(
            Observation(
                id=uuid.uuid4(),
                case_id=test_case.id,
                tool_name="tool",
                normalized_content={"msg": "1"},
                timestamp_utc=base_time,
            )
        )
        db_session.commit()

        # offset >= total
        resp_offset = service.get_paginated_timeline(test_case.id, limit=10, offset=5)
        assert resp_offset.total == 1
        assert resp_offset.items == []
        assert resp_offset.has_more is False
