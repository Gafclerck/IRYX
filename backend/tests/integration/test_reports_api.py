"""Integration tests for sealed report consultation and download (Story 8.4)."""

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from iryx.audit.models import AuditEvent
from iryx.auth.models import MembershipRole, User
from iryx.auth.schemas import UserCreate
from iryx.auth.services import UserService
from iryx.cases.models import Case
from iryx.core.security import create_access_token
from iryx.organizations.services import OrganizationService
from iryx.reporting.models import Report
from iryx.reporting.schemas import ReportFormat, ReportStatus
from iryx.reporting.services import ReportService


@pytest.fixture
def reports_setup(db_session: Session) -> dict[str, Any]:
    """Create two isolated cases with validated, draft, exported and foreign reports."""
    user_service = UserService(db_session)
    organization_service = OrganizationService(db_session)

    admin = user_service.create_user(
        UserCreate(email="reports-admin@cert.fr", password="Password123!")
    )
    member = user_service.create_user(
        UserCreate(email="reports-member@cert.fr", password="Password123!")
    )
    outsider = user_service.create_user(
        UserCreate(email="reports-outsider@cert.fr", password="Password123!")
    )
    organization = organization_service.create_organization(
        name="CERT Rapports", creator_id=admin.id
    )
    organization_service.add_member(
        org_id=organization.id, user_id=member.id, role=MembershipRole.VIEWER
    )

    case = Case(
        organization_id=organization.id,
        title="Dossier rapports scellés",
        created_by=admin.id,
    )
    db_session.add(case)
    db_session.commit()

    other_admin = user_service.create_user(
        UserCreate(email="reports-other@external.fr", password="Password123!")
    )
    other_organization = organization_service.create_organization(
        name="CERT Externe", creator_id=other_admin.id
    )
    other_case = Case(
        organization_id=other_organization.id,
        title="Dossier étranger",
        created_by=other_admin.id,
    )
    db_session.add(other_case)
    db_session.commit()

    def _add_report(
        case_id: uuid.UUID,
        report_format: ReportFormat,
        report_status: ReportStatus,
        version: int,
        content: str,
    ) -> Report:
        row = Report(
            case_id=case_id,
            format=report_format.value,
            status=report_status.value,
            version=version,
            content=content,
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            generation_id=str(uuid.uuid4()),
            created_at=datetime(2026, 11, 26, 10, version, tzinfo=UTC),
        )
        db_session.add(row)
        return row

    markdown = _add_report(
        case.id, ReportFormat.MARKDOWN, ReportStatus.VALIDATED, 1, "# Rapport scellé v1\n\nRésumé."
    )
    json_report = _add_report(
        case.id,
        ReportFormat.JSON,
        ReportStatus.VALIDATED,
        1,
        '{"version": 1, "resume": "Rapport JSON"}',
    )
    markdown_v2 = _add_report(
        case.id,
        ReportFormat.MARKDOWN,
        ReportStatus.VALIDATED,
        2,
        "# Rapport scellé v2\n\nNouvelle version.",
    )
    draft = _add_report(
        case.id, ReportFormat.MARKDOWN, ReportStatus.DRAFT, 3, "# Brouillon non publié"
    )
    exported = _add_report(
        case.id, ReportFormat.JSON, ReportStatus.EXPORTED, 2, '{"export": "ancien"}'
    )
    foreign = _add_report(
        other_case.id,
        ReportFormat.MARKDOWN,
        ReportStatus.VALIDATED,
        1,
        "SECRET OTHER CASE",
    )
    db_session.commit()

    return {
        "case": case,
        "other_case": other_case,
        "member": member,
        "outsider": outsider,
        "other_admin": other_admin,
        "markdown": markdown,
        "json": json_report,
        "markdown_v2": markdown_v2,
        "draft": draft,
        "exported": exported,
        "foreign": foreign,
    }


def _auth_header(user: User) -> dict[str, str]:
    """Build a Bearer header for the given user."""
    token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return {"Authorization": f"Bearer {token}"}


def _list_url(case_id: uuid.UUID | str) -> str:
    """Return the sealed-report listing endpoint for a case."""
    return f"/api/v1/cases/{case_id}/reports"


def _download_url(case_id: uuid.UUID | str, report_id: uuid.UUID | str) -> str:
    """Return the sealed-report download endpoint for a case and report."""
    return f"/api/v1/cases/{case_id}/reports/{report_id}/download"


def test_openapi_exposes_both_report_paths(client: TestClient) -> None:
    """Verify the two Story 8.4 GET paths are registered on the application."""
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    assert "get" in paths[_list_url("{case_id}")]
    download = paths[_download_url("{case_id}", "{report_id}")]["get"]
    response_200 = download["responses"]["200"]
    assert set(response_200["content"]) == {"text/markdown", "application/json"}
    header_schema = response_200["headers"]["X-Report-SHA256"]["schema"]
    assert header_schema["type"] == "string"
    assert header_schema["pattern"] == "^[0-9a-f]{64}$"


def test_list_reports_nominal_envelope_and_validation_filter(
    client: TestClient, reports_setup: dict[str, Any]
) -> None:
    """Verify a member sees only validated reports of their case in a paged envelope."""
    case: Case = reports_setup["case"]
    markdown: Report = reports_setup["markdown"]
    json_report: Report = reports_setup["json"]
    markdown_v2: Report = reports_setup["markdown_v2"]

    response = client.get(_list_url(case.id), headers=_auth_header(reports_setup["member"]))

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["total_items"] == 3
    assert data["limit"] == 50
    assert data["offset"] == 0
    assert data["has_more"] is False
    assert [item["version"] for item in data["items"]] == [1, 1, 2]
    assert [item["format"] for item in data["items"]] == ["json", "markdown", "markdown"]
    assert {item["id"] for item in data["items"]} == {
        str(markdown.id),
        str(json_report.id),
        str(markdown_v2.id),
    }
    assert all(item["status"] == "validated" for item in data["items"])
    assert all(item["case_id"] == str(case.id) for item in data["items"])
    assert all(len(item["sha256"]) == 64 for item in data["items"])
    assert all("content" in item for item in data["items"])


def test_list_reports_pagination_and_format_filter(
    client: TestClient, reports_setup: dict[str, Any]
) -> None:
    """Verify deterministic pagination and format filtering keep global totals."""
    case: Case = reports_setup["case"]
    headers = _auth_header(reports_setup["member"])

    page = client.get(
        _list_url(case.id), params={"limit": 1, "offset": 1}, headers=headers
    )
    assert page.status_code == 200
    data = page.json()
    assert data["total"] == 3
    assert data["limit"] == 1
    assert data["offset"] == 1
    assert data["has_more"] is True
    assert [item["id"] for item in data["items"]] == [str(reports_setup["markdown"].id)]

    last_page = client.get(
        _list_url(case.id), params={"limit": 1, "offset": 3}, headers=headers
    )
    assert last_page.status_code == 200
    assert last_page.json()["items"] == []
    assert last_page.json()["has_more"] is False

    markdown_only = client.get(
        _list_url(case.id), params={"format": "markdown"}, headers=headers
    )
    assert markdown_only.status_code == 200
    assert markdown_only.json()["total"] == 2
    assert {item["format"] for item in markdown_only.json()["items"]} == {"markdown"}

    json_only = client.get(
        _list_url(case.id), params={"format": "json"}, headers=headers
    )
    assert json_only.status_code == 200
    assert json_only.json()["total"] == 1
    assert [item["id"] for item in json_only.json()["items"]] == [
        str(reports_setup["json"].id)
    ]


@pytest.mark.parametrize(
    ("report_key", "media_type"),
    [
        ("markdown", "text/markdown"),
        ("json", "application/json"),
    ],
)
def test_download_report_nominal_headers_exact_bytes_and_no_mutation(
    client: TestClient,
    db_session: Session,
    reports_setup: dict[str, Any],
    report_key: str,
    media_type: str,
) -> None:
    """Verify the served body and headers match the sealed row without any write."""
    report: Report = reports_setup[report_key]
    expected_content = report.content
    expected_sha256 = report.sha256

    response = client.get(
        _download_url(reports_setup["case"].id, report.id),
        headers=_auth_header(reports_setup["member"]),
    )

    assert response.status_code == 200
    assert response.content == expected_content.encode("utf-8")
    assert response.headers["X-Report-SHA256"] == expected_sha256
    assert response.headers["Content-Type"] == media_type

    db_session.expire_all()
    db_session.refresh(report)
    assert report.status == ReportStatus.VALIDATED.value
    assert report.content == expected_content
    assert report.sha256 == expected_sha256
    assert db_session.scalar(select(AuditEvent)) is None


@pytest.mark.parametrize("report_key", ["missing", "foreign", "draft", "exported"])
def test_download_unavailable_report_returns_404_without_leaking_content(
    client: TestClient, reports_setup: dict[str, Any], report_key: str
) -> None:
    """Verify absent, foreign and non-validated reports are indistinguishable 404s."""
    report_id = (
        uuid.uuid4() if report_key == "missing" else reports_setup[report_key].id
    )

    response = client.get(
        _download_url(reports_setup["case"].id, report_id),
        headers=_auth_header(reports_setup["member"]),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "REPORT_NOT_FOUND"
    assert "SECRET OTHER CASE" not in response.text
    assert "Brouillon non publié" not in response.text


def test_non_member_is_forbidden_before_any_report_read(
    client: TestClient, reports_setup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify verify_case_access blocks outsiders before ReportService reads a row."""

    def _must_not_read(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Un rapport a été lu pour un utilisateur non membre.")

    monkeypatch.setattr(ReportService, "get_report", _must_not_read)
    monkeypatch.setattr(ReportService, "list_reports", _must_not_read)
    headers = _auth_header(reports_setup["outsider"])

    list_response = client.get(_list_url(reports_setup["case"].id), headers=headers)
    download_response = client.get(
        _download_url(reports_setup["case"].id, reports_setup["markdown"].id),
        headers=headers,
    )

    for response in (list_response, download_response):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"


def test_unknown_case_returns_case_not_found(
    client: TestClient, reports_setup: dict[str, Any]
) -> None:
    """Verify a valid but unknown case UUID is rejected as CASE_NOT_FOUND."""
    headers = _auth_header(reports_setup["member"])
    unknown_case_id = uuid.uuid4()

    list_response = client.get(_list_url(unknown_case_id), headers=headers)
    download_response = client.get(
        _download_url(unknown_case_id, reports_setup["markdown"].id), headers=headers
    )

    for response in (list_response, download_response):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CASE_NOT_FOUND"


def test_malformed_uuids_return_invalid_uuid(
    client: TestClient, reports_setup: dict[str, Any]
) -> None:
    """Verify malformed case or report identifiers are rejected before any read."""
    headers = _auth_header(reports_setup["member"])

    responses = [
        client.get(_list_url("not-a-uuid"), headers=headers),
        client.get(
            _download_url("not-a-uuid", reports_setup["markdown"].id), headers=headers
        ),
        client.get(
            _download_url(reports_setup["case"].id, "not-a-uuid"), headers=headers
        ),
    ]

    for response in responses:
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_UUID"


def test_invalid_format_returns_invalid_report_format(
    client: TestClient, reports_setup: dict[str, Any]
) -> None:
    """Verify an unsupported report format exposes the dedicated validation code."""
    response = client.get(
        _list_url(reports_setup["case"].id),
        params={"format": "pdf"},
        headers=_auth_header(reports_setup["member"]),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REPORT_FORMAT"


@pytest.mark.parametrize(
    "invalid_query", ["limit=0", "limit=101", "offset=-1"]
)
def test_list_reports_pagination_limits_validation(
    client: TestClient,
    reports_setup: dict[str, Any],
    invalid_query: str,
) -> None:
    """Verify out-of-range pagination returns HTTP 422 VALIDATION_ERROR."""
    response = client.get(
        f"{_list_url(reports_setup['case'].id)}?{invalid_query}",
        headers=_auth_header(reports_setup["member"]),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "url_builder",
    [
        lambda case: _list_url(case.id),
        lambda case: _download_url(case.id, uuid.uuid4()),
    ],
)
@pytest.mark.parametrize(
    ("headers", "expected_code"),
    [
        ({}, "UNAUTHORIZED"),
        ({"Authorization": "Bearer invalid-token"}, "INVALID_TOKEN"),
    ],
)
def test_report_endpoints_require_authentication(
    client: TestClient,
    reports_setup: dict[str, Any],
    url_builder: Any,
    headers: dict[str, str],
    expected_code: str,
) -> None:
    """Verify missing or invalid Bearer tokens return HTTP 401 on both endpoints."""
    response = client.get(url_builder(reports_setup["case"]), headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == expected_code
