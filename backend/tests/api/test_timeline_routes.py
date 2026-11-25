"""Integration tests for Timeline API endpoint (/api/v1/cases/{case_id}/timeline).

Validates Story 7.2 requirements, NFR-PERF-07, and Invariant 2.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from iryx.analytics.models import Observation
from iryx.auth.models import MembershipRole, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.models import Case
from iryx.core.security import create_access_token
from iryx.evidence.models import Evidence
from iryx.organizations.services import OrganizationService


@pytest.fixture
def test_setup(db_session: Session) -> dict[str, object]:
    """Create test organization, users, and cases for tenant isolation testing."""
    user_svc = UserService(db_session)
    org_svc = OrganizationService(db_session)

    admin = user_svc.create_user(UserCreate(email="admin@soc.iryx", password="Password123!"))
    investigator = user_svc.create_user(
        UserCreate(email="investigator@soc.iryx", password="Password123!")
    )
    analyst = user_svc.create_user(UserCreate(email="analyst@soc.iryx", password="Password123!"))
    viewer = user_svc.create_user(UserCreate(email="viewer@soc.iryx", password="Password123!"))
    outsider = user_svc.create_user(UserCreate(email="outsider@soc.iryx", password="Password123!"))

    # Create Org 1
    org = org_svc.create_organization(name="CERT Interne", creator_id=admin.id)
    org_svc.add_member(org_id=org.id, user_id=investigator.id, role=MembershipRole.INVESTIGATOR)
    org_svc.add_member(org_id=org.id, user_id=analyst.id, role=MembershipRole.ANALYST)
    org_svc.add_member(org_id=org.id, user_id=viewer.id, role=MembershipRole.VIEWER)

    case = Case(organization_id=org.id, title="Affaire Ransomware", created_by=investigator.id)
    db_session.add(case)
    db_session.commit()

    # Create Org 2 for tenant isolation
    other_admin = user_svc.create_user(
        UserCreate(email="other_admin@external.iryx", password="Password123!")
    )
    other_org = org_svc.create_organization(name="CERT Externe", creator_id=other_admin.id)
    other_case = Case(
        organization_id=other_org.id, title="Affaire Concurrente", created_by=other_admin.id
    )
    db_session.add(other_case)
    db_session.commit()

    # Create sample evidences in case 1
    evidence1 = Evidence(
        id=uuid.uuid4(),
        case_id=case.id,
        original_name="Security.evtx",
        file_size=1024 * 1024,
        sha256="1" * 64,
        detected_type="application/x-winevtx",
    )
    evidence2 = Evidence(
        id=uuid.uuid4(),
        case_id=case.id,
        original_name="SYSTEM.hive",
        file_size=512 * 1024,
        sha256="2" * 64,
        detected_type="application/x-registry-hive",
    )
    db_session.add_all([evidence1, evidence2])
    db_session.commit()

    return {
        "org": org,
        "other_org": other_org,
        "case": case,
        "other_case": other_case,
        "admin": admin,
        "investigator": investigator,
        "analyst": analyst,
        "viewer": viewer,
        "outsider": outsider,
        "other_admin": other_admin,
        "evidence1": evidence1,
        "evidence2": evidence2,
    }


def auth_header(user: User) -> dict[str, str]:
    """Generate Authorization header with Bearer JWT for specified user."""
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# 1. Nominal Paginated Timeline Consultation & Ordering
# =========================================================================


def test_get_timeline_nominal_pagination(
    client: TestClient, db_session: Session, test_setup: dict
) -> None:
    """Verify nominal timeline pagination with default limit=50, total counters and has_more."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    evidence1: Evidence = test_setup["evidence1"]

    base_time = datetime(2026, 11, 23, 8, 0, 0, tzinfo=UTC)
    observations = []
    for i in range(60):
        obs = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            source_id=evidence1.id,
            tool_name="python-evtx",
            normalized_content={"event_id": 4624, "message": f"Logon event #{i}"},
            timestamp_utc=base_time + timedelta(minutes=i),
        )
        observations.append(obs)
    db_session.add_all(observations)
    db_session.commit()

    # Page 1: limit=50, offset=0
    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline?limit=50&offset=0",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "items" in data
    assert "events" in data
    assert len(data["items"]) == 50
    assert len(data["events"]) == 50
    assert data["total"] == 60
    assert data["total_items"] == 60
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert data["has_more"] is True

    # Page 2: limit=50, offset=50
    resp_page2 = client.get(
        f"/api/v1/cases/{case.id}/timeline?limit=50&offset=50",
        headers=auth_header(analyst),
    )
    assert resp_page2.status_code == 200
    data_page2 = resp_page2.json()
    assert len(data_page2["items"]) == 10
    assert data_page2["total"] == 60
    assert data_page2["total_items"] == 60
    assert data_page2["offset"] == 50
    assert data_page2["has_more"] is False


def test_get_timeline_chronological_ordering_utc(
    client: TestClient, db_session: Session, test_setup: dict
) -> None:
    """Verify deterministic chronological ordering by timestamp_utc ASC, id ASC."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    evidence1: Evidence = test_setup["evidence1"]

    base_time = datetime(2026, 11, 23, 10, 0, 0, tzinfo=UTC)

    # Insert events in reverse chronological order
    times = [
        base_time + timedelta(hours=3),
        base_time + timedelta(hours=1),
        base_time + timedelta(hours=4),
        base_time,
        base_time + timedelta(hours=2),
    ]
    for _i, t in enumerate(times):
        obs = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            source_id=evidence1.id,
            tool_name="python-evtx",
            normalized_content={"message": f"Event at {t.isoformat()}"},
            timestamp_utc=t,
        )
        db_session.add(obs)
    db_session.commit()

    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 5

    # Verify strictly non-decreasing timestamps
    timestamps = [datetime.fromisoformat(item["timestamp_utc"]) for item in items]
    assert timestamps == sorted(timestamps)


# =========================================================================
# 2. Time Window Filtering & Validation
# =========================================================================


def test_get_timeline_filter_time_window(
    client: TestClient, db_session: Session, test_setup: dict
) -> None:
    """Verify filtering by start_time and end_time restricts returned events."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    evidence1: Evidence = test_setup["evidence1"]

    base_time = datetime(2026, 11, 23, 8, 0, 0, tzinfo=UTC)
    for hour in range(8):
        obs = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            source_id=evidence1.id,
            tool_name="python-evtx",
            normalized_content={"hour": hour},
            timestamp_utc=base_time + timedelta(hours=hour),
        )
        db_session.add(obs)
    db_session.commit()

    # Filter between 10:00 and 12:00 (hours 2, 3, 4 -> 3 events)
    start_str = "2026-11-23T10:00:00Z"
    end_str = "2026-11-23T12:00:00Z"
    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline?start_time={start_str}&end_time={end_str}",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    for item in data["items"]:
        dt = datetime.fromisoformat(item["timestamp_utc"])
        assert datetime(2026, 11, 23, 10, 0, 0, tzinfo=UTC) <= dt <= datetime(
            2026, 11, 23, 12, 0, 0, tzinfo=UTC
        )


def test_get_timeline_inverted_time_window_returns_422(
    client: TestClient, test_setup: dict
) -> None:
    """Verify start_time > end_time returns HTTP 422 with explicit message."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    start_str = "2026-11-23T14:00:00Z"
    end_str = "2026-11-23T10:00:00Z"

    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline?start_time={start_str}&end_time={end_str}",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "start_time must be before end_time" in data["error"]["message"]


# =========================================================================
# 3. Filtering by Tool & Source Evidence
# =========================================================================


def test_get_timeline_filter_by_tool_name(
    client: TestClient, db_session: Session, test_setup: dict
) -> None:
    """Verify tool_name filter restricts results to observations from that tool."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    evidence1: Evidence = test_setup["evidence1"]

    base_time = datetime(2026, 11, 23, 9, 0, 0, tzinfo=UTC)
    tools = ["python-evtx", "volatility", "python-evtx", "regipy"]
    for i, tool in enumerate(tools):
        obs = Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            source_id=evidence1.id,
            tool_name=tool,
            normalized_content={"tool": tool},
            timestamp_utc=base_time + timedelta(minutes=i),
        )
        db_session.add(obs)
    db_session.commit()

    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline?tool_name=python-evtx",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(item["tool_name"] == "python-evtx" for item in data["items"])


def test_get_timeline_filter_by_evidence_id(
    client: TestClient, db_session: Session, test_setup: dict
) -> None:
    """Verify evidence_id filter restricts results to observations linked to that evidence."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    evidence1: Evidence = test_setup["evidence1"]
    evidence2: Evidence = test_setup["evidence2"]

    base_time = datetime(2026, 11, 23, 9, 0, 0, tzinfo=UTC)

    obs1 = Observation(
        id=uuid.uuid4(),
        case_id=case.id,
        source_id=evidence1.id,
        tool_name="python-evtx",
        normalized_content={"message": "From evidence 1"},
        timestamp_utc=base_time,
    )
    obs2 = Observation(
        id=uuid.uuid4(),
        case_id=case.id,
        source_id=evidence2.id,
        tool_name="regipy",
        normalized_content={"message": "From evidence 2"},
        timestamp_utc=base_time + timedelta(minutes=5),
    )
    db_session.add_all([obs1, obs2])
    db_session.commit()

    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline?evidence_id={evidence1.id}",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["evidence_id"] == str(evidence1.id)
    assert data["items"][0]["evidence_name"] == "Security.evtx"


# =========================================================================
# 4. Pagination Validation & Edge Cases
# =========================================================================


@pytest.mark.parametrize(
    "invalid_query",
    [
        "limit=0",
        "limit=101",
        "offset=-1",
    ],
)
def test_get_timeline_invalid_pagination_returns_422(
    client: TestClient, test_setup: dict, invalid_query: str
) -> None:
    """Verify invalid pagination bounds return HTTP 422."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]

    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline?{invalid_query}",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 422


# =========================================================================
# 5. Security & Multi-Tenant Isolation
# =========================================================================


def test_get_timeline_unauthenticated_returns_401(client: TestClient, test_setup: dict) -> None:
    """Verify unauthenticated requests return HTTP 401."""
    case: Case = test_setup["case"]
    resp = client.get(f"/api/v1/cases/{case.id}/timeline")
    assert resp.status_code == 401


def test_get_timeline_cross_organization_forbidden(
    client: TestClient, test_setup: dict
) -> None:
    """Verify user from another organization receives HTTP 403."""
    case: Case = test_setup["case"]
    other_admin: User = test_setup["other_admin"]

    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline",
        headers=auth_header(other_admin),
    )
    assert resp.status_code == 403


def test_get_timeline_case_not_found_returns_404(client: TestClient, test_setup: dict) -> None:
    """Verify non-existent case returns HTTP 404."""
    analyst: User = test_setup["analyst"]
    random_case_id = uuid.uuid4()

    resp = client.get(
        f"/api/v1/cases/{random_case_id}/timeline",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 404


# =========================================================================
# 6. Invariant 2 & Read-Only Verification
# =========================================================================


def test_timeline_invariant_2_disallows_mutation_endpoints(
    client: TestClient, test_setup: dict
) -> None:
    """Invariant 2: Verify timeline route is strictly read-only (rejects mutations with 405)."""
    case: Case = test_setup["case"]
    admin: User = test_setup["admin"]

    timeline_url = f"/api/v1/cases/{case.id}/timeline"

    resp_post = client.post(timeline_url, json={"event": "fake"}, headers=auth_header(admin))
    assert resp_post.status_code == 405

    resp_put = client.put(timeline_url, json={"event": "fake"}, headers=auth_header(admin))
    assert resp_put.status_code == 405

    resp_patch = client.patch(timeline_url, json={"event": "fake"}, headers=auth_header(admin))
    assert resp_patch.status_code == 405

    resp_delete = client.delete(timeline_url, headers=auth_header(admin))
    assert resp_delete.status_code == 405


def test_get_timeline_excludes_undated_observations(
    client: TestClient, db_session: Session, test_setup: dict
) -> None:
    """Invariant 2 & FR24: Undated observations are excluded from chronological timeline."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    evidence1: Evidence = test_setup["evidence1"]

    base_time = datetime(2026, 11, 23, 10, 0, 0, tzinfo=UTC)

    obs_dated = Observation(
        id=uuid.uuid4(),
        case_id=case.id,
        source_id=evidence1.id,
        tool_name="python-evtx",
        normalized_content={"message": "Dated event"},
        timestamp_utc=base_time,
    )
    obs_undated = Observation(
        id=uuid.uuid4(),
        case_id=case.id,
        source_id=evidence1.id,
        tool_name="python-evtx",
        normalized_content={"message": "Undated fact"},
        timestamp_utc=None,
    )
    db_session.add_all([obs_dated, obs_undated])
    db_session.commit()

    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["observation_id"] == str(obs_dated.id)


def test_get_timeline_deterministic_tie_breaking_identical_timestamps(
    client: TestClient, db_session: Session, test_setup: dict
) -> None:
    """Verify tie-breaking on identical timestamps is strictly ordered by observation id ASC."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    evidence1: Evidence = test_setup["evidence1"]

    same_time = datetime(2026, 11, 23, 10, 0, 0, tzinfo=UTC)
    id1 = uuid.UUID("00000000-0000-0000-0000-000000000010")
    id2 = uuid.UUID("00000000-0000-0000-0000-000000000020")
    id3 = uuid.UUID("00000000-0000-0000-0000-000000000030")

    # Insert in reversed order
    for oid in [id3, id1, id2]:
        obs = Observation(
            id=oid,
            case_id=case.id,
            source_id=evidence1.id,
            tool_name="python-evtx",
            normalized_content={"msg": f"event {oid}"},
            timestamp_utc=same_time,
        )
        db_session.add(obs)
    db_session.commit()

    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    returned_ids = [item["observation_id"] for item in data["items"]]
    assert returned_ids == [str(id1), str(id2), str(id3)]


def test_get_timeline_point_in_time_start_equals_end(
    client: TestClient, db_session: Session, test_setup: dict
) -> None:
    """Verify point-in-time query where start_time == end_time returns matching events."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    evidence1: Evidence = test_setup["evidence1"]

    target_time = datetime(2026, 11, 23, 12, 0, 0, tzinfo=UTC)
    before_time = target_time - timedelta(minutes=10)
    after_time = target_time + timedelta(minutes=10)

    for t in [before_time, target_time, after_time]:
        db_session.add(
            Observation(
                id=uuid.uuid4(),
                case_id=case.id,
                source_id=evidence1.id,
                tool_name="python-evtx",
                normalized_content={"msg": str(t)},
                timestamp_utc=t,
            )
        )
    db_session.commit()

    iso_str = "2026-11-23T12:00:00Z"
    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline?start_time={iso_str}&end_time={iso_str}",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["timestamp_utc"] == iso_str


def test_get_timeline_single_bounded_queries(
    client: TestClient, db_session: Session, test_setup: dict
) -> None:
    """Verify single-bounded queries (start_time only or end_time only)."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    evidence1: Evidence = test_setup["evidence1"]

    base_time = datetime(2026, 11, 23, 10, 0, 0, tzinfo=UTC)
    for i in range(5):
        db_session.add(
            Observation(
                id=uuid.uuid4(),
                case_id=case.id,
                source_id=evidence1.id,
                tool_name="python-evtx",
                normalized_content={"i": i},
                timestamp_utc=base_time + timedelta(hours=i),
            )
        )
    db_session.commit()

    # start_time only (>= 12:00 -> hours 2, 3, 4 -> 3 events)
    resp_start = client.get(
        f"/api/v1/cases/{case.id}/timeline?start_time=2026-11-23T12:00:00Z",
        headers=auth_header(analyst),
    )
    assert resp_start.status_code == 200
    assert resp_start.json()["total"] == 3

    # end_time only (<= 11:00 -> hours 0, 1 -> 2 events)
    resp_end = client.get(
        f"/api/v1/cases/{case.id}/timeline?end_time=2026-11-23T11:00:00Z",
        headers=auth_header(analyst),
    )
    assert resp_end.status_code == 200
    assert resp_end.json()["total"] == 2


def test_get_timeline_combined_all_filters(
    client: TestClient, db_session: Session, test_setup: dict
) -> None:
    """Verify combining start_time, end_time, tool_name and evidence_id."""
    case: Case = test_setup["case"]
    analyst: User = test_setup["analyst"]
    evidence1: Evidence = test_setup["evidence1"]
    evidence2: Evidence = test_setup["evidence2"]

    t1 = datetime(2026, 11, 23, 10, 0, 0, tzinfo=UTC)

    # Matching event
    match_obs = Observation(
        id=uuid.uuid4(),
        case_id=case.id,
        source_id=evidence1.id,
        tool_name="python-evtx",
        normalized_content={"status": "match"},
        timestamp_utc=t1,
    )
    # Wrong tool
    wrong_tool = Observation(
        id=uuid.uuid4(),
        case_id=case.id,
        source_id=evidence1.id,
        tool_name="regipy",
        normalized_content={"status": "wrong_tool"},
        timestamp_utc=t1,
    )
    # Wrong evidence
    wrong_ev = Observation(
        id=uuid.uuid4(),
        case_id=case.id,
        source_id=evidence2.id,
        tool_name="python-evtx",
        normalized_content={"status": "wrong_ev"},
        timestamp_utc=t1,
    )
    # Outside time window
    wrong_time = Observation(
        id=uuid.uuid4(),
        case_id=case.id,
        source_id=evidence1.id,
        tool_name="python-evtx",
        normalized_content={"status": "wrong_time"},
        timestamp_utc=datetime(2026, 11, 23, 15, 0, 0, tzinfo=UTC),
    )
    db_session.add_all([match_obs, wrong_tool, wrong_ev, wrong_time])
    db_session.commit()

    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline"
        f"?start_time=2026-11-23T09:00:00Z"
        f"&end_time=2026-11-23T11:00:00Z"
        f"&tool_name=python-evtx"
        f"&evidence_id={evidence1.id}",
        headers=auth_header(analyst),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["observation_id"] == str(match_obs.id)


def test_get_timeline_viewer_role_access(
    client: TestClient, db_session: Session, test_setup: dict
) -> None:
    """Verify users with VIEWER role can consult the timeline (read-only projection)."""
    case: Case = test_setup["case"]
    viewer: User = test_setup["viewer"]
    evidence1: Evidence = test_setup["evidence1"]

    db_session.add(
        Observation(
            id=uuid.uuid4(),
            case_id=case.id,
            source_id=evidence1.id,
            tool_name="python-evtx",
            normalized_content={"msg": "read by viewer"},
            timestamp_utc=datetime(2026, 11, 23, 10, 0, 0, tzinfo=UTC),
        )
    )
    db_session.commit()

    resp = client.get(
        f"/api/v1/cases/{case.id}/timeline",
        headers=auth_header(viewer),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
