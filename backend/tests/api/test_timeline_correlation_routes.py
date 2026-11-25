"""Integration tests for Timeline Correlation API routes (Story 7.3).

Tests:
- GET /api/v1/cases/{case_id}/timeline/correlations (HTTP 200, 401, 403, 404)
- GET /api/v1/cases/{case_id}/timeline with correlation enrichments and filters
- Multi-tenant isolation and strict status exclusion (REJECTED, PROPOSED)
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from iryx.analytics.models import (
    Finding,
    FindingConfidence,
    FindingSeverity,
    FindingStatus,
    FindingType,
    Observation,
)
from iryx.auth.models import MembershipRole, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.models import Case
from iryx.core.security import create_access_token
from iryx.evidence.models import Evidence
from iryx.organizations.services import OrganizationService


@pytest.fixture
def correlation_setup(db_session: Session) -> dict[str, object]:
    """Create test organization, users, cases, and evidences for correlation testing."""
    user_svc = UserService(db_session)
    org_svc = OrganizationService(db_session)

    admin = user_svc.create_user(UserCreate(email="admin-corr@soc.iryx", password="Password123!"))
    analyst = user_svc.create_user(
        UserCreate(email="analyst-corr@soc.iryx", password="Password123!")
    )
    viewer = user_svc.create_user(UserCreate(email="viewer-corr@soc.iryx", password="Password123!"))
    outsider = user_svc.create_user(
        UserCreate(email="outsider-corr@soc.iryx", password="Password123!")
    )

    org = org_svc.create_organization(name="CERT Correlation Test Unit", creator_id=admin.id)
    org_svc.add_member(org_id=org.id, user_id=analyst.id, role=MembershipRole.ANALYST)
    org_svc.add_member(org_id=org.id, user_id=viewer.id, role=MembershipRole.VIEWER)

    case = Case(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Affaire APT Correlation",
        created_by=analyst.id,
    )
    db_session.add(case)

    # Isolated other organization and case
    other_admin = user_svc.create_user(
        UserCreate(email="other-admin@ext.iryx", password="Password123!")
    )
    other_org = org_svc.create_organization(name="Other CERT", creator_id=other_admin.id)
    other_case = Case(
        id=uuid.uuid4(),
        organization_id=other_org.id,
        title="Other Case",
        created_by=other_admin.id,
    )
    db_session.add(other_case)

    # Evidences for case 1
    evidence_evtx = Evidence(
        id=uuid.uuid4(),
        case_id=case.id,
        original_name="Security.evtx",
        file_size=1024 * 1024,
        sha256="1" * 64,
        detected_type="application/x-winevtx",
    )
    evidence_prefetch = Evidence(
        id=uuid.uuid4(),
        case_id=case.id,
        original_name="MALWARE.pf",
        file_size=512 * 1024,
        sha256="2" * 64,
        detected_type="application/x-prefetch",
    )
    db_session.add_all([evidence_evtx, evidence_prefetch])
    db_session.commit()

    return {
        "org": org,
        "other_org": other_org,
        "case": case,
        "other_case": other_case,
        "admin": admin,
        "analyst": analyst,
        "viewer": viewer,
        "outsider": outsider,
        "other_admin": other_admin,
        "evidence_evtx": evidence_evtx,
        "evidence_prefetch": evidence_prefetch,
    }


def auth_header(user: User) -> dict[str, str]:
    """Generate Authorization header with Bearer JWT for specified user."""
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


class TestTimelineCorrelationRoutes:
    """Integration test suite for timeline correlation endpoints."""

    def test_correlations_unauthenticated_returns_401(
        self, client: TestClient, correlation_setup: dict[str, object]
    ) -> None:
        """GET /api/v1/cases/{case_id}/timeline/correlations without token returns HTTP 401."""
        case: Case = correlation_setup["case"]  # type: ignore[assignment]
        url = f"/api/v1/cases/{case.id}/timeline/correlations"
        resp = client.get(url)
        assert resp.status_code == 401

    def test_correlations_case_not_found_returns_404(
        self, client: TestClient, correlation_setup: dict[str, object]
    ) -> None:
        """GET /api/v1/cases/{unknown_id}/timeline/correlations returns HTTP 404."""
        analyst: User = correlation_setup["analyst"]  # type: ignore[assignment]
        url = f"/api/v1/cases/{uuid.uuid4()}/timeline/correlations"
        resp = client.get(url, headers=auth_header(analyst))
        assert resp.status_code == 404

    def test_correlations_forbidden_for_outsider_returns_403(
        self, client: TestClient, correlation_setup: dict[str, object]
    ) -> None:
        """GET /api/v1/cases/{case_id}/timeline/correlations by non-member returns HTTP 403."""
        case: Case = correlation_setup["case"]  # type: ignore[assignment]
        outsider: User = correlation_setup["outsider"]  # type: ignore[assignment]
        url = f"/api/v1/cases/{case.id}/timeline/correlations"
        resp = client.get(url, headers=auth_header(outsider))
        assert resp.status_code == 403

    def test_correlations_empty_case_returns_200(
        self, client: TestClient, correlation_setup: dict[str, object]
    ) -> None:
        """GET /api/v1/cases/{case_id}/timeline/correlations on case without correlations.

        Returns HTTP 200 with empty list.
        """
        case: Case = correlation_setup["case"]  # type: ignore[assignment]
        analyst: User = correlation_setup["analyst"]  # type: ignore[assignment]
        url = f"/api/v1/cases/{case.id}/timeline/correlations"
        resp = client.get(url, headers=auth_header(analyst))
        assert resp.status_code == 200
        data = resp.json()
        assert data["case_id"] == str(case.id)
        assert data["total"] == 0
        assert data["correlations"] == []
        assert data["groups"] == []
        assert data["items"] == []

    def test_correlations_nominal_multi_sources_http_200(
        self,
        client: TestClient,
        db_session: Session,
        correlation_setup: dict[str, object],
    ) -> None:
        """Nominal test: Validated finding linking Prefetch and EVTX at same minute

        returns HTTP 200 with structured correlation group and shared correlation marker.
        """
        case: Case = correlation_setup["case"]  # type: ignore[assignment]
        analyst: User = correlation_setup["analyst"]  # type: ignore[assignment]
        ev_evtx: Evidence = correlation_setup["evidence_evtx"]  # type: ignore[assignment]
        ev_pf: Evidence = correlation_setup["evidence_prefetch"]  # type: ignore[assignment]

        base_time = datetime(2026, 11, 25, 10, 30, 0, tzinfo=UTC)

        obs_pf = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            tool_name="dissect",
            source_id=ev_pf.id,
            source_location=r"C:\Windows\Prefetch\EXPLOIT.EXE-ABCDE.pf",
            normalized_content={"executable_name": "EXPLOIT.EXE", "run_count": 2},
            timestamp_utc=base_time,
        )
        obs_evtx = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            tool_name="python-evtx",
            source_id=ev_evtx.id,
            source_location="Event 4688",
            normalized_content={"event_id": 4688, "process_name": "EXPLOIT.EXE"},
            timestamp_utc=base_time + timedelta(seconds=15),
        )
        db_session.add_all([obs_pf, obs_evtx])

        finding = Finding(
            id=uuid.uuid4(),
            case_id=case.id,
            title="Correlated Execution: Exploit.exe via Prefetch and Process Creation",
            severity=FindingSeverity.HIGH,
            confidence=FindingConfidence.HIGH,
            finding_type=FindingType.FACT,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs_pf.id, obs_evtx.id],
        )
        db_session.add(finding)
        db_session.commit()

        # 1. Check correlations endpoint
        url_corr = f"/api/v1/cases/{case.id}/timeline/correlations"
        resp_corr = client.get(url_corr, headers=auth_header(analyst))
        assert resp_corr.status_code == 200
        data_corr = resp_corr.json()

        assert data_corr["total"] == 1
        group = data_corr["correlations"][0]
        expected_marker = f"corr-{finding.id}"
        assert group["correlation_marker"] == expected_marker
        assert group["correlation_id"] == expected_marker
        assert group["finding_id"] == str(finding.id)
        assert group["finding_title"] == finding.title
        assert group["finding"]["id"] == str(finding.id)
        assert group["is_multi_tool"] is True
        assert group["is_multi_source"] is True
        assert set(group["tools"]) == {"dissect", "python-evtx"}
        assert len(group["events"]) == 2

        for evt in group["events"]:
            assert evt["correlation_marker"] == expected_marker
            assert evt["is_correlated"] is True
            assert len(evt["findings"]) == 1
            assert evt["findings"][0]["id"] == str(finding.id)

        # 2. Check main timeline endpoint: events must be enriched
        url_tl = f"/api/v1/cases/{case.id}/timeline"
        resp_tl = client.get(url_tl, headers=auth_header(analyst))
        assert resp_tl.status_code == 200
        data_tl = resp_tl.json()

        assert data_tl["total"] == 2
        for evt in data_tl["items"]:
            assert evt["correlation_marker"] == expected_marker
            assert evt["is_correlated"] is True
            assert len(evt["findings"]) == 1
            assert evt["findings"][0]["id"] == str(finding.id)

    def test_correlations_strictly_excludes_rejected_and_proposed_findings(
        self,
        client: TestClient,
        db_session: Session,
        correlation_setup: dict[str, object],
    ) -> None:
        """Ensure findings with status rejected and proposed are never superimposed on timeline."""
        case: Case = correlation_setup["case"]  # type: ignore[assignment]
        analyst: User = correlation_setup["analyst"]  # type: ignore[assignment]
        ev_evtx: Evidence = correlation_setup["evidence_evtx"]  # type: ignore[assignment]
        ev_pf: Evidence = correlation_setup["evidence_prefetch"]  # type: ignore[assignment]

        base_time = datetime(2026, 11, 25, 11, 0, 0, tzinfo=UTC)

        obs1 = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            tool_name="dissect",
            source_id=ev_pf.id,
            normalized_content={"cmd": "rejected.exe"},
            timestamp_utc=base_time,
        )
        obs2 = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            tool_name="python-evtx",
            source_id=ev_evtx.id,
            normalized_content={"cmd": "proposed.exe"},
            timestamp_utc=base_time + timedelta(seconds=10),
        )
        db_session.add_all([obs1, obs2])

        finding_rejected = Finding(
            id=uuid.uuid4(),
            case_id=case.id,
            title="Rejected finding",
            severity=FindingSeverity.LOW,
            status=FindingStatus.REJECTED,
            observation_refs=[obs1.id],
        )
        finding_proposed = Finding(
            id=uuid.uuid4(),
            case_id=case.id,
            title="Proposed finding",
            severity=FindingSeverity.MEDIUM,
            status=FindingStatus.PROPOSED,
            observation_refs=[obs2.id],
        )
        db_session.add_all([finding_rejected, finding_proposed])
        db_session.commit()

        # Correlations endpoint: 0 groups
        resp_corr = client.get(
            f"/api/v1/cases/{case.id}/timeline/correlations",
            headers=auth_header(analyst),
        )
        assert resp_corr.status_code == 200
        assert resp_corr.json()["total"] == 0

        # Timeline endpoint: events must NOT have findings or correlation markers
        resp_tl = client.get(
            f"/api/v1/cases/{case.id}/timeline",
            headers=auth_header(analyst),
        )
        assert resp_tl.status_code == 200
        data_tl = resp_tl.json()
        assert data_tl["total"] == 2
        for evt in data_tl["items"]:
            assert evt["findings"] == []
            assert evt["correlation_marker"] is None
            assert evt["is_correlated"] is False

    def test_timeline_query_filtering_by_correlation_params(
        self,
        client: TestClient,
        db_session: Session,
        correlation_setup: dict[str, object],
    ) -> None:
        """Test filtering the timeline via is_correlated, correlation_marker, and finding_id."""
        case: Case = correlation_setup["case"]  # type: ignore[assignment]
        analyst: User = correlation_setup["analyst"]  # type: ignore[assignment]
        ev_evtx: Evidence = correlation_setup["evidence_evtx"]  # type: ignore[assignment]
        ev_pf: Evidence = correlation_setup["evidence_prefetch"]  # type: ignore[assignment]

        base_time = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)

        obs_corr1 = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            tool_name="dissect",
            source_id=ev_pf.id,
            normalized_content={"msg": "corr1"},
            timestamp_utc=base_time,
        )
        obs_corr2 = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            tool_name="python-evtx",
            source_id=ev_evtx.id,
            normalized_content={"msg": "corr2"},
            timestamp_utc=base_time + timedelta(seconds=20),
        )
        obs_solo = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            tool_name="python-evtx",
            source_id=ev_evtx.id,
            normalized_content={"msg": "solo"},
            timestamp_utc=base_time + timedelta(seconds=40),
        )
        db_session.add_all([obs_corr1, obs_corr2, obs_solo])

        finding = Finding(
            id=uuid.uuid4(),
            case_id=case.id,
            title="Correlated finding",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs_corr1.id, obs_corr2.id],
        )
        db_session.add(finding)
        db_session.commit()

        marker = f"corr-{finding.id}"

        # 1. Filter is_correlated=true
        r1 = client.get(
            f"/api/v1/cases/{case.id}/timeline?is_correlated=true",
            headers=auth_header(analyst),
        )
        assert r1.status_code == 200
        assert r1.json()["total"] == 2

        # 2. Filter is_correlated=false
        r2 = client.get(
            f"/api/v1/cases/{case.id}/timeline?is_correlated=false",
            headers=auth_header(analyst),
        )
        assert r2.status_code == 200
        assert r2.json()["total"] == 1
        assert r2.json()["items"][0]["observation_id"] == str(obs_solo.id)

        # 3. Filter correlation_marker
        r3 = client.get(
            f"/api/v1/cases/{case.id}/timeline?correlation_marker={marker}",
            headers=auth_header(analyst),
        )
        assert r3.status_code == 200
        assert r3.json()["total"] == 2

        # 4. Filter finding_id
        r4 = client.get(
            f"/api/v1/cases/{case.id}/timeline?finding_id={finding.id}",
            headers=auth_header(analyst),
        )
        assert r4.status_code == 200
        assert r4.json()["total"] == 2

    def test_viewer_can_read_correlations(
        self,
        client: TestClient,
        correlation_setup: dict[str, object],
    ) -> None:
        """Viewer role in the same organization can consult timeline correlations."""
        case: Case = correlation_setup["case"]  # type: ignore[assignment]
        viewer: User = correlation_setup["viewer"]  # type: ignore[assignment]

        resp = client.get(
            f"/api/v1/cases/{case.id}/timeline/correlations",
            headers=auth_header(viewer),
        )
        assert resp.status_code == 200

    def test_timeline_query_filtering_by_correlated_only(
        self,
        client: TestClient,
        db_session: Session,
        correlation_setup: dict[str, object],
    ) -> None:
        """Test GET /api/v1/cases/{case_id}/timeline with correlated_only filters."""
        case: Case = correlation_setup["case"]  # type: ignore[assignment]
        analyst: User = correlation_setup["analyst"]  # type: ignore[assignment]
        ev_evtx: Evidence = correlation_setup["evidence_evtx"]  # type: ignore[assignment]
        ev_pf: Evidence = correlation_setup["evidence_prefetch"]  # type: ignore[assignment]

        base_time = datetime(2026, 11, 25, 14, 0, 0, tzinfo=UTC)

        obs_corr1 = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            tool_name="dissect",
            source_id=ev_pf.id,
            normalized_content={"msg": "corr1"},
            timestamp_utc=base_time,
        )
        obs_corr2 = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            tool_name="python-evtx",
            source_id=ev_evtx.id,
            normalized_content={"msg": "corr2"},
            timestamp_utc=base_time + timedelta(seconds=20),
        )
        obs_solo = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            tool_name="python-evtx",
            source_id=ev_evtx.id,
            normalized_content={"msg": "solo"},
            timestamp_utc=base_time + timedelta(seconds=40),
        )
        db_session.add_all([obs_corr1, obs_corr2, obs_solo])

        finding = Finding(
            id=uuid.uuid4(),
            case_id=case.id,
            title="Correlated finding for correlated_only test",
            severity=FindingSeverity.HIGH,
            status=FindingStatus.VALIDATED,
            observation_refs=[obs_corr1.id, obs_corr2.id],
        )
        db_session.add(finding)
        db_session.commit()

        # 1. Test correlated_only=true
        resp_true = client.get(
            f"/api/v1/cases/{case.id}/timeline?correlated_only=true",
            headers=auth_header(analyst),
        )
        assert resp_true.status_code == 200
        assert resp_true.json()["total"] == 2
        for item in resp_true.json()["items"]:
            assert item["is_correlated"] is True

        # 2. Test correlated_only=false
        resp_false = client.get(
            f"/api/v1/cases/{case.id}/timeline?correlated_only=false",
            headers=auth_header(analyst),
        )
        assert resp_false.status_code == 200
        assert resp_false.json()["total"] == 1
        assert resp_false.json()["items"][0]["observation_id"] == str(obs_solo.id)
        assert resp_false.json()["items"][0]["is_correlated"] is False
