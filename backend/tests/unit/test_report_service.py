"""Unit tests for report generation invariants (Story 8.3)."""

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from iryx.analytics.models import (
    Finding,
    FindingConfidence,
    FindingSeverity,
    FindingStatus,
    FindingType,
    Observation,
)
from iryx.audit.models import AuditEvent
from iryx.auth.models import Membership, MembershipRole, Organization, User
from iryx.cases.models import Case
from iryx.core.exceptions import (
    InsufficientPermissionsException,
    ReportGenerationFailedException,
    ValidationException,
)
from iryx.evidence.models import Evidence
from iryx.reporting.models import Report
from iryx.reporting.pseudonymizer import DeterministicPseudonymizer
from iryx.reporting.schemas import (
    CANONICAL_SECTION_KEYS,
    CANONICAL_SECTION_TITLES,
    ReportContent,
    ReportFormat,
    ReportSection,
    ReportStatus,
)
from iryx.reporting.services import _MAX_VERSION_RETRIES, ReportService

_VALIDATED_TITLE = "Connexion suspecte depuis 192.168.1.50"
_PROPOSED_TITLE = "Hypothèse non validée confidentielle"
_OTHER_TITLE = "Constat d'un autre dossier"


class FakeLLMClient:
    """Instrumented external drafting double."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[list[dict[str, Any]]] = []
        self.role = "rapporteur"

    def for_role(self, role: Any) -> "FakeLLMClient":
        """Return itself with the requested role recorded."""
        self.requested_role = role
        return self

    async def complete(self, messages: list[dict[str, Any]], temperature: float = 0.0) -> dict:
        """Record the request and return a canned response."""
        self.calls.append(messages)
        return {"content": self.response}


def _llm_response(**overrides: str) -> str:
    """Return a complete eight-section JSON draft."""
    keys = (
        "resume_managerial",
        "perimetre",
        "methodologie",
        "chaine_des_preuves",
        "observations",
        "constats_valides",
        "chronologie",
        "limites",
    )
    payload = {key: "Texte factuel." for key in keys}
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def _structured_content(case_id: uuid.UUID) -> ReportContent:
    """Build a complete canonical ReportContent for a given case."""
    return ReportContent(
        case_id=case_id,
        version=1,
        sections=[
            ReportSection(key=key, title=title, content="Contenu structuré.")
            for key, title in zip(CANONICAL_SECTION_KEYS, CANONICAL_SECTION_TITLES, strict=True)
        ],
    )


@pytest.fixture
def setup(db_session: Session) -> dict[str, Any]:
    """Create two isolated cases with findings, evidence and observations."""
    import iryx.audit.models  # noqa: F401
    import iryx.gateway.models  # noqa: F401
    import iryx.orchestrator.models  # noqa: F401
    import iryx.reporting.models  # noqa: F401

    org = Organization(name="Report Service Org")
    other_org = Organization(name="Other Org")
    user = User(email=f"report-svc-{uuid.uuid4()}@cert.fr", hashed_password="pw")
    outsider = User(email=f"outsider-{uuid.uuid4()}@other.fr", hashed_password="pw")
    db_session.add_all([org, other_org, user, outsider])
    db_session.flush()
    db_session.add(
        Membership(
            organization_id=org.id,
            user_id=user.id,
            role=MembershipRole.INVESTIGATOR,
        )
    )
    case = Case(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Dossier principal",
        description="Incident avec constats validés",
        created_by=user.id,
    )
    other_case = Case(
        id=uuid.uuid4(),
        organization_id=other_org.id,
        title="Dossier étranger",
        description="Données à ne jamais divulguer",
        created_by=outsider.id,
    )
    db_session.add_all([case, other_case])
    db_session.flush()

    evidence = Evidence(
        case_id=case.id,
        original_name="auth.log",
        file_size=1024,
        sha256="b" * 64,
        detected_type="text/plain",
    )
    other_evidence = Evidence(
        case_id=other_case.id,
        original_name="secret.log",
        file_size=2048,
        sha256="c" * 64,
        detected_type="text/plain",
    )
    observation = Observation(
        case_id=case.id,
        tool_name="log_parser",
        source_id=evidence.id,
        normalized_content={"event": "failed_login"},
        timestamp_utc=datetime(2026, 11, 25, 10, 0, tzinfo=UTC),
    )
    other_observation = Observation(
        case_id=other_case.id,
        tool_name="other_parser",
        normalized_content={"event": "secret"},
        timestamp_utc=datetime(2026, 11, 25, 11, 0, tzinfo=UTC),
    )
    validated = Finding(
        case_id=case.id,
        title=_VALIDATED_TITLE,
        severity=FindingSeverity.HIGH,
        confidence=FindingConfidence.HIGH,
        finding_type=FindingType.FACT,
        status=FindingStatus.VALIDATED,
    )
    proposed = Finding(
        case_id=case.id,
        title=_PROPOSED_TITLE,
        severity=FindingSeverity.CRITICAL,
        confidence=FindingConfidence.LOW,
        finding_type=FindingType.HYPOTHESIS,
        status=FindingStatus.PROPOSED,
    )
    other_finding = Finding(
        case_id=other_case.id,
        title=_OTHER_TITLE,
        severity=FindingSeverity.CRITICAL,
        status=FindingStatus.VALIDATED,
    )
    db_session.add_all(
        [
            evidence,
            other_evidence,
            observation,
            other_observation,
            validated,
            proposed,
            other_finding,
        ]
    )
    db_session.commit()
    return {
        "case": case,
        "other_case": other_case,
        "user": user,
        "outsider": outsider,
        "evidence": evidence,
        "validated": validated,
    }


def _reports_for(db_session: Session, case_id: uuid.UUID) -> list[Report]:
    """Return all report rows of one case ordered deterministically."""
    return list(
        db_session.scalars(
            select(Report).where(Report.case_id == case_id).order_by(Report.format)
        ).all()
    )


def test_generate_report_persists_two_sealed_validated_rows(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify both formats are sealed, validated and contain only case-scoped valid data."""
    rows = ReportService(db_session).generate_report(case_id=setup["case"].id, internal=True)

    assert len(rows) == 2
    assert {row.format for row in rows} == {"markdown", "json"}
    assert {row.status for row in rows} == {ReportStatus.VALIDATED.value}
    assert len({row.generation_id for row in rows}) == 1
    assert {row.version for row in rows} == {1}
    for row in rows:
        assert row.sha256 == hashlib.sha256(row.content.encode("utf-8")).hexdigest()
        assert _VALIDATED_TITLE in row.content
        assert "high" in row.content.lower()
        assert "auth.log" in row.content
        assert "log_parser" in row.content
        assert _PROPOSED_TITLE not in row.content
        assert _OTHER_TITLE not in row.content
        assert "secret.log" not in row.content
        assert db_session.scalar(select(AuditEvent)) is None

    hashes = {row.format: row.sha256 for row in rows}
    assert hashes[ReportFormat.MARKDOWN.value] != hashes[ReportFormat.JSON.value]


@pytest.mark.parametrize(
    ("requested_status", "succeeds"),
    [
        (ReportStatus.DRAFT.value, False),
        (ReportStatus.EXPORTED.value, False),
        (ReportStatus.VALIDATED.value, True),
    ],
)
def test_generate_report_status_guard(
    db_session: Session,
    setup: dict[str, Any],
    requested_status: str,
    succeeds: bool,
) -> None:
    """Verify only 'validated' can be requested and rejected requests persist nothing."""
    service = ReportService(db_session)
    if succeeds:
        rows = service.generate_report(
            case_id=setup["case"].id, internal=True, status=requested_status
        )
        assert len(rows) == 2
        assert {row.status for row in rows} == {ReportStatus.VALIDATED.value}
        assert len(_reports_for(db_session, setup["case"].id)) == 2
    else:
        with pytest.raises(ReportGenerationFailedException, match="validated"):
            service.generate_report(
                case_id=setup["case"].id, internal=True, status=requested_status
            )
        assert _reports_for(db_session, setup["case"].id) == []


def test_validated_title_containing_proposed_title_is_accepted(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify a proposed title nested inside a validated title is not rejected."""
    case_id = setup["case"].id
    db_session.add_all(
        [
            Finding(
                case_id=case_id,
                title="Connexion",
                severity=FindingSeverity.MEDIUM,
                status=FindingStatus.PROPOSED,
            ),
            Finding(
                case_id=case_id,
                title="Connexion suspecte depuis le serveur",
                severity=FindingSeverity.HIGH,
                status=FindingStatus.VALIDATED,
            ),
        ]
    )
    db_session.commit()

    rows = ReportService(db_session).generate_report(case_id=case_id, internal=True)

    assert len(rows) == 2
    assert all("Connexion suspecte depuis le serveur" in row.content for row in rows)


def test_two_validated_severities_appear_in_both_persisted_formats(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify distinct severities survive into both sealed documents."""
    case_id = setup["case"].id
    medium_title = "Anomalie de configuration confirmée"
    critical_title = "Compromission avérée du serveur"
    db_session.add_all(
        [
            Finding(
                case_id=case_id,
                title=medium_title,
                severity=FindingSeverity.MEDIUM,
                status=FindingStatus.VALIDATED,
            ),
            Finding(
                case_id=case_id,
                title=critical_title,
                severity=FindingSeverity.CRITICAL,
                status=FindingStatus.VALIDATED,
            ),
        ]
    )
    db_session.commit()

    rows = ReportService(db_session).generate_report(case_id=case_id, internal=True)
    documents = {row.format: row.content for row in rows}

    assert set(documents) == {ReportFormat.MARKDOWN.value, ReportFormat.JSON.value}
    for document in documents.values():
        assert f"[medium] {medium_title}" in document
        assert f"[critical] {critical_title}" in document


def test_caller_cannot_fix_generation_id_and_regeneration_bumps_version(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify caller values are ignored and each generation gets fresh identity."""
    service = ReportService(db_session)
    first = service.generate_report(
        case_id=setup["case"].id,
        internal=True,
        generation_id="caller-fixed-id",
        sha256="f" * 64,
    )
    second = service.generate_report(
        case_id=setup["case"].id,
        internal=True,
        generation_id="caller-fixed-id",
    )

    assert first[0].generation_id != "caller-fixed-id"
    assert second[0].generation_id != "caller-fixed-id"
    assert first[0].generation_id != second[0].generation_id
    assert {row.version for row in first} == {1}
    assert {row.version for row in second} == {2}
    assert all(row.sha256 != "f" * 64 for row in first)


@pytest.mark.parametrize("invalid_case_id", ["not-a-uuid", "", "00000000-0000-0000-0000-z"])
def test_invalid_case_id_is_wrapped(
    db_session: Session, invalid_case_id: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify malformed identifiers are enveloped and never logged verbatim."""
    with (
        caplog.at_level(logging.ERROR, logger="iryx.reporting.services"),
        pytest.raises(ReportGenerationFailedException) as exc_info,
    ):
        ReportService(db_session).generate_report(case_id=invalid_case_id, internal=True)

    assert exc_info.value.code == "REPORT_GENERATION_FAILED"
    assert "identifiant invalide" in str(exc_info.value)
    redacted = [
        record
        for record in caplog.records
        if getattr(record, "context", {}).get("case_id") == "<invalid>"
    ]
    assert len(redacted) == 1
    assert redacted[0].getMessage() == "Report generation failed: ValidationException"
    if invalid_case_id:
        assert invalid_case_id not in str(redacted[0].getMessage())
        assert invalid_case_id not in caplog.text


def test_external_mode_requires_an_injected_pseudonymizer(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify the service does not instantiate a fresh pseudonymizer on approval."""
    with pytest.raises(ReportGenerationFailedException, match="Pseudonymiseur"):
        ReportService(db_session).generate_report(
            case_id=setup["case"].id,
            internal=True,
            h3_approved=True,
        )
    assert _reports_for(db_session, setup["case"].id) == []


def test_external_mode_uses_shared_pseudonymizer_and_llm(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify approved external drafting uses the injected store and role."""
    pseudonymizer = DeterministicPseudonymizer()
    client = FakeLLMClient(_llm_response())
    rows = ReportService(db_session).generate_report(
        case_id=setup["case"].id,
        internal=True,
        h3_approved=True,
        pseudonymizer=pseudonymizer,
        llm_client=client,
    )
    assert len(rows) == 2
    assert len(client.calls) == 1
    # An already RAPPORTEUR-scoped client is used directly, not rebuilt.
    assert not hasattr(client, "requested_role")
    assert client.role == "rapporteur"
    assert "Connexion suspecte depuis" in rows[0].content


def test_service_rejects_unvalidated_title_returned_by_llm(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify a proposed finding title cannot be sealed in any format."""
    client = FakeLLMClient(
        _llm_response(observations=f"Détail : {_PROPOSED_TITLE}.")
    )
    with pytest.raises(ReportGenerationFailedException):
        ReportService(db_session).generate_report(
            case_id=setup["case"].id,
            internal=True,
            h3_approved=True,
            pseudonymizer=DeterministicPseudonymizer(),
            llm_client=client,
        )
    assert _reports_for(db_session, setup["case"].id) == []


def test_rejected_explicit_verdict_forces_local_mode(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify an explicit H3 rejection blocks any external client call."""
    client = FakeLLMClient(_llm_response())
    rows = ReportService(db_session).generate_report(
        case_id=setup["case"].id,
        internal=True,
        h3_approved=True,
        h3_rejected=True,
        llm_client=client,
    )
    assert len(rows) == 2
    assert client.calls == []


def test_outsider_cannot_generate_list_or_update(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify authorization rejects outsiders before any report is exposed."""
    case_id = setup["case"].id
    service = ReportService(db_session)
    with pytest.raises(InsufficientPermissionsException):
        service.generate_report(case_id=case_id, user_id=setup["outsider"].id)
    with pytest.raises(InsufficientPermissionsException):
        service.list_reports(case_id=case_id, user_id=setup["outsider"].id)
    with pytest.raises(InsufficientPermissionsException):
        service.update_report(
            report_id=uuid.uuid4(),
            content="contenu",
            case_id=case_id,
            user_id=setup["outsider"].id,
        )
    assert _reports_for(db_session, case_id) == []


def test_authorized_member_can_list_and_scope_reports(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify a member can list only their own case reports."""
    service = ReportService(db_session)
    service.generate_report(case_id=setup["case"].id, internal=True)
    reported = service.list_reports(
        case_id=setup["case"].id, user_id=setup["user"].id
    )
    assert len(reported) == 2
    assert all(row.case_id == setup["case"].id for row in reported)
    with pytest.raises(InsufficientPermissionsException):
        service.list_reports(
            case_id=setup["other_case"].id, user_id=setup["user"].id
        )


def test_list_reports_filters_by_markdown_format(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify format filtering returns only rows of the requested format."""
    service = ReportService(db_session)
    generated = service.generate_report(case_id=setup["case"].id, internal=True)
    assert {row.format for row in generated} == {
        ReportFormat.MARKDOWN.value,
        ReportFormat.JSON.value,
    }

    rows = service.list_reports(
        case_id=setup["case"].id,
        user_id=setup["user"].id,
        format=ReportFormat.MARKDOWN,
    )
    assert [row.format for row in rows] == [ReportFormat.MARKDOWN.value]


def test_update_report_draft_only_and_no_promotion(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify drafts can be re-sealed but never promoted to validated or exported."""
    service = ReportService(db_session)
    draft = Report(
        case_id=setup["case"].id,
        format=ReportFormat.MARKDOWN.value,
        content="ancien contenu",
        sha256="0" * 64,
        status=ReportStatus.DRAFT.value,
        generation_id=str(uuid.uuid4()),
        version=5,
    )
    db_session.add(draft)
    db_session.commit()

    updated = service.update_report(
        report_id=draft.id,
        content="nouveau contenu",
        case_id=setup["case"].id,
        internal=True,
    )
    assert updated.content == "nouveau contenu"
    assert updated.sha256 == hashlib.sha256(b"nouveau contenu").hexdigest()
    assert updated.status == ReportStatus.DRAFT.value

    for status in (ReportStatus.VALIDATED.value, ReportStatus.EXPORTED.value):
        with pytest.raises(ReportGenerationFailedException):
            service.update_report(
                report_id=draft.id,
                content="contenu arbitraire",
                case_id=setup["case"].id,
                internal=True,
                status=status,
            )

    validated = Report(
        case_id=setup["case"].id,
        format=ReportFormat.JSON.value,
        content="contenu validé",
        sha256=hashlib.sha256("contenu validé".encode()).hexdigest(),
        status=ReportStatus.VALIDATED.value,
        generation_id=str(uuid.uuid4()),
        version=6,
    )
    db_session.add(validated)
    db_session.commit()
    with pytest.raises(ReportGenerationFailedException):
        service.update_report(
            report_id=validated.id,
            content="écrit",
            case_id=setup["case"].id,
            internal=True,
        )


def test_version_conflict_retries_with_new_generation(
    db_session: Session,
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a unique-constraint conflict triggers a fresh generation and version."""
    existing = Report(
        case_id=setup["case"].id,
        format=ReportFormat.MARKDOWN.value,
        content="ancien rapport",
        sha256=hashlib.sha256(b"ancien rapport").hexdigest(),
        status=ReportStatus.VALIDATED.value,
        generation_id="already-used",
        version=1,
    )
    db_session.add(existing)
    db_session.commit()

    service = ReportService(db_session)
    generation_ids: list[str] = []

    def _next_generation_id() -> str:
        value = str(uuid.uuid4())
        generation_ids.append(value)
        return value

    monkeypatch.setattr(service, "_new_generation_id", _next_generation_id)
    monkeypatch.setattr(service, "_allocate_version", lambda _case_id: 1)
    with pytest.raises(ReportGenerationFailedException):
        service.generate_report(
            case_id=setup["case"].id,
            internal=True,
            generation_id="caller-ignored",
        )
    assert len(generation_ids) == _MAX_VERSION_RETRIES
    assert len(set(generation_ids)) == _MAX_VERSION_RETRIES

    monkeypatch.setattr(service, "_allocate_version", lambda _case_id: 2)
    rows = service.generate_report(
        case_id=setup["case"].id,
        internal=True,
        generation_id="caller-ignored",
    )
    assert {row.version for row in rows} == {2}
    assert all(row.generation_id not in {"already-used", "caller-ignored"} for row in rows)


def test_version_conflict_retries_within_one_generation(
    db_session: Session,
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a stale allocation retries inside one call with a fresh generation."""
    existing = Report(
        case_id=setup["case"].id,
        format=ReportFormat.MARKDOWN.value,
        content="rapport existant",
        sha256=hashlib.sha256(b"rapport existant").hexdigest(),
        status=ReportStatus.VALIDATED.value,
        generation_id="already-used",
        version=1,
    )
    db_session.add(existing)
    db_session.commit()
    original = (
        existing.content,
        existing.sha256,
        existing.generation_id,
        existing.version,
        existing.status,
    )

    service = ReportService(db_session)
    allocations = iter([1, 2])
    monkeypatch.setattr(service, "_allocate_version", lambda _case_id: next(allocations))

    rows = service.generate_report(
        case_id=setup["case"].id,
        internal=True,
        generation_id="caller-ignored",
    )

    assert {row.version for row in rows} == {2}
    assert len({row.generation_id for row in rows}) == 1
    assert all(row.generation_id not in {"already-used", "caller-ignored"} for row in rows)

    db_session.expire_all()
    db_session.refresh(existing)
    assert (
        existing.content,
        existing.sha256,
        existing.generation_id,
        existing.version,
        existing.status,
    ) == original


def test_second_insert_failure_rolls_back_the_pair(
    db_session: Session,
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify no validated row survives a failure while adding the second format."""
    service = ReportService(db_session)
    original_add = db_session.add
    calls = {"count": 0}

    def _failing_add(instance: object) -> None:
        calls["count"] += 1
        if calls["count"] > 1 and isinstance(instance, Report):
            raise RuntimeError("insert failed")
        original_add(instance)

    monkeypatch.setattr(db_session, "add", _failing_add)
    with pytest.raises(ReportGenerationFailedException):
        service.generate_report(case_id=setup["case"].id, internal=True)
    assert _reports_for(db_session, setup["case"].id) == []


def test_refresh_failure_after_commit_is_not_reported(
    db_session: Session,
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify a post-commit refresh failure never turns into a false generation error."""
    monkeypatch.setattr(
        db_session, "refresh", lambda _instance: (_ for _ in ()).throw(RuntimeError("refresh"))
    )
    rows = ReportService(db_session).generate_report(
        case_id=setup["case"].id, internal=True
    )
    assert len(rows) == 2
    assert len(_reports_for(db_session, setup["case"].id)) == 2


def test_report_out_maps_persisted_generation_id(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify the public schema accepts the string generation_id stored in the DB."""
    rows = ReportService(db_session).generate_report(case_id=setup["case"].id, internal=True)
    out = ReportService.to_out(rows[0])
    assert out.id == rows[0].id
    assert str(out.generation_id) == rows[0].generation_id
    assert out.sha256 == rows[0].sha256
    assert out.created_at is not None


def test_sealed_documents_carry_the_persisted_generation_metadata(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify both formats seal the same metadata allocated for the persisted rows."""
    rows = ReportService(db_session).generate_report(case_id=setup["case"].id, internal=True)
    markdown = next(row for row in rows if row.format == ReportFormat.MARKDOWN.value)
    json_row = next(row for row in rows if row.format == ReportFormat.JSON.value)

    assert rows[0].generation_id == rows[1].generation_id
    assert rows[0].version == rows[1].version == 1
    assert f"- Génération : {rows[0].generation_id}" in markdown.content
    assert "- Version : 1" in markdown.content
    generated_at = datetime.fromisoformat(
        next(
            line.split(": ", 1)[1]
            for line in markdown.content.splitlines()
            if line.startswith("- Généré le : ")
        )
    )
    assert generated_at.replace(tzinfo=None) == markdown.created_at.replace(tzinfo=None)

    payload = json.loads(json_row.content)
    assert payload["generation_id"] == rows[0].generation_id
    assert payload["version"] == rows[0].version
    assert payload["created_at"] == generated_at.isoformat()


def test_caller_cannot_override_db_derived_context(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify reserved context keys stay DB-derived and rejection sets only grow."""
    service = ReportService(db_session)
    rows = service.generate_report(
        case_id=setup["case"].id,
        internal=True,
        case={"title": "titre inventé"},
        evidences=[],
        observations=[],
        timeline=[],
        facts=[],
        incident_description="description inventée",
    )
    assert all(_VALIDATED_TITLE in row.content for row in rows)
    assert all("auth.log" in row.content for row in rows)
    assert all("log_parser" in row.content for row in rows)
    assert all("titre inventé" not in row.content for row in rows)

    # The caller's empty timeline cannot erase the DB-projected observation
    # (seeded at 2026-11-25T10:00:00Z with summary "event=failed_login").
    json_row = _reports_for(db_session, setup["case"].id)[0]
    assert json_row.format == ReportFormat.JSON.value
    chronologie = next(
        section["content"]
        for section in json.loads(json_row.content)["sections"]
        if section["key"] == "chronologie"
    )
    assert "2026-11-25T10:00:00" in chronologie
    assert "event=failed_login" in chronologie

    client = FakeLLMClient(_llm_response(observations=f"Voir {_PROPOSED_TITLE}."))
    with pytest.raises(ReportGenerationFailedException):
        service.generate_report(
            case_id=setup["case"].id,
            internal=True,
            h3_approved=True,
            pseudonymizer=DeterministicPseudonymizer(),
            llm_client=client,
            invalid_finding_titles=[],
        )
    assert len(_reports_for(db_session, setup["case"].id)) == 2


def test_non_boolean_rejected_verdict_is_not_a_rejection(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify ``"false"`` never forces local mode in the service."""
    client = FakeLLMClient(_llm_response())
    rows = ReportService(db_session).generate_report(
        case_id=setup["case"].id,
        internal=True,
        h3_approved=True,
        h3_rejected="false",
        local_report_mode="false",
        pseudonymizer=DeterministicPseudonymizer(),
        llm_client=client,
    )
    assert len(client.calls) == 1
    assert len(rows) == 2


def test_service_failure_is_typed_with_report_generation_failed(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify a service failure exposes the documented code and HTTP status."""
    with pytest.raises(ReportGenerationFailedException) as exc_info:
        ReportService(db_session).generate_report(
            case_id=setup["case"].id,
            internal=True,
            h3_approved=True,
        )
    assert exc_info.value.code == "REPORT_GENERATION_FAILED"
    assert exc_info.value.status_code == 500


def test_regeneration_leaves_the_first_pair_bit_for_bit_unchanged(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify a new version never mutates or rewrites an earlier sealed pair."""
    service = ReportService(db_session)
    first = service.generate_report(case_id=setup["case"].id, internal=True)
    before = {
        row.id: (row.content, row.sha256, row.generation_id, row.version, row.status)
        for row in first
    }
    second = service.generate_report(case_id=setup["case"].id, internal=True)
    assert {row.version for row in second} == {2}
    assert {row.generation_id for row in second} != {row.generation_id for row in first}

    db_session.expire_all()
    reloaded = {
        row.id: (row.content, row.sha256, row.generation_id, row.version, row.status)
        for row in db_session.scalars(
            select(Report).where(Report.case_id == setup["case"].id)
        )
        if row.id in before
    }
    assert reloaded == before


def test_deterministic_concurrent_allocations_produce_one_pair_per_version(
    db_session: Session,
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify two racers that receive distinct versions seal two distinct pairs."""
    service = ReportService(db_session)
    allocations = iter([1, 2])
    monkeypatch.setattr(service, "_allocate_version", lambda _case_id: next(allocations))

    first = service.generate_report(case_id=setup["case"].id, internal=True)
    second = service.generate_report(case_id=setup["case"].id, internal=True)

    assert {row.version for row in first} == {1}
    assert {row.version for row in second} == {2}
    assert {row.generation_id for row in first}.isdisjoint(
        {row.generation_id for row in second}
    )
    assert len(_reports_for(db_session, setup["case"].id)) == 4


def test_non_version_integrity_error_is_not_retried(
    db_session: Session,
    setup: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify only the version uniqueness violation triggers the retry loop."""
    service = ReportService(db_session)
    commits = {"count": 0}

    def _failing_commit() -> None:
        commits["count"] += 1
        raise IntegrityError(
            "INSERT INTO reports",
            {},
            RuntimeError("CHECK constraint failed: ck_reports_sha256_hex_check"),
        )

    monkeypatch.setattr(db_session, "commit", _failing_commit)
    with pytest.raises(ReportGenerationFailedException, match="unicité inattendu"):
        service.generate_report(case_id=setup["case"].id, internal=True)
    assert commits["count"] == 1
    db_session.rollback()
    assert _reports_for(db_session, setup["case"].id) == []


def test_generate_report_with_missing_case_raises_validation_exception(
    db_session: Session,
) -> None:
    """Verify a valid UUID for an unknown case stays a CASE_NOT_FOUND validation error."""
    with pytest.raises(ValidationException, match="Dossier introuvable") as exc_info:
        ReportService(db_session).generate_report(case_id=uuid.uuid4(), internal=True)
    assert exc_info.value.code == "CASE_NOT_FOUND"


def test_outsider_cannot_update_without_a_case_id(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify an unscoped update is refused before any report row is read."""
    with pytest.raises(ValidationException):
        ReportService(db_session).update_report(
            report_id=uuid.uuid4(),
            content="contenu",
            case_id=None,  # type: ignore[arg-type]
            user_id=setup["outsider"].id,
        )


def test_update_report_rejects_structured_content_from_another_case(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify a structured body cannot be used to move a draft across cases."""
    service = ReportService(db_session)
    draft = Report(
        case_id=setup["case"].id,
        format=ReportFormat.MARKDOWN.value,
        content="ancien contenu",
        sha256="0" * 64,
        status=ReportStatus.DRAFT.value,
        generation_id=str(uuid.uuid4()),
        version=5,
    )
    db_session.add(draft)
    db_session.commit()

    with pytest.raises(ReportGenerationFailedException, match="autre dossier"):
        service.update_report(
            report_id=draft.id,
            content=_structured_content(setup["other_case"].id),
            case_id=setup["case"].id,
            internal=True,
        )
    db_session.refresh(draft)
    assert draft.content == "ancien contenu"


def test_list_reports_with_malformed_case_id_raises_validation_exception(
    db_session: Session,
) -> None:
    """Verify an invalid identifier is a 422-level error, not a generation failure."""
    with pytest.raises(ValidationException, match="case_id invalide"):
        ReportService(db_session).list_reports(case_id="not-a-uuid", internal=True)


def test_update_report_raw_string_rejects_unvalidated_title(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify the raw-string path applies the same validated-findings rule."""
    draft = Report(
        case_id=setup["case"].id,
        format=ReportFormat.MARKDOWN.value,
        content="ancien contenu",
        sha256="0" * 64,
        status=ReportStatus.DRAFT.value,
        generation_id=str(uuid.uuid4()),
        version=3,
    )
    db_session.add(draft)
    db_session.commit()

    with pytest.raises(ReportGenerationFailedException, match="non validé"):
        ReportService(db_session).update_report(
            report_id=draft.id,
            content=f"Analyse : {_PROPOSED_TITLE}.",
            case_id=setup["case"].id,
            internal=True,
        )
    db_session.refresh(draft)
    assert draft.content == "ancien contenu"


def test_update_report_structured_metadata_agrees_with_the_row(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify a structured draft update seals the persisted generation identity."""
    generation_id = str(uuid.uuid4())
    draft = Report(
        case_id=setup["case"].id,
        format=ReportFormat.JSON.value,
        content="ancien contenu",
        sha256="0" * 64,
        status=ReportStatus.DRAFT.value,
        generation_id=generation_id,
        version=7,
        created_at=datetime(2026, 1, 2, 3, 4, tzinfo=UTC),
    )
    db_session.add(draft)
    db_session.commit()

    updated = ReportService(db_session).update_report(
        report_id=draft.id,
        content=_structured_content(setup["case"].id),
        case_id=setup["case"].id,
        internal=True,
    )
    payload = json.loads(updated.content)
    assert payload["generation_id"] == generation_id
    assert payload["version"] == 7
    assert payload["created_at"] == updated.created_at.isoformat()
    assert updated.sha256 == hashlib.sha256(updated.content.encode("utf-8")).hexdigest()


def test_update_report_structured_metadata_rejects_unvalidated_title(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify caller metadata serialized into the final document is validated too."""
    draft = Report(
        case_id=setup["case"].id,
        format=ReportFormat.JSON.value,
        content="ancien contenu",
        sha256="0" * 64,
        status=ReportStatus.DRAFT.value,
        generation_id=str(uuid.uuid4()),
        version=8,
    )
    db_session.add(draft)
    db_session.commit()

    structured = _structured_content(setup["case"].id)
    structured.metadata = {"note": _PROPOSED_TITLE}
    with pytest.raises(ReportGenerationFailedException, match="non validé"):
        ReportService(db_session).update_report(
            report_id=draft.id,
            content=structured,
            case_id=setup["case"].id,
            internal=True,
        )
    db_session.refresh(draft)
    assert draft.content == "ancien contenu"


def test_list_reports_with_malformed_format_raises_validation_exception(
    db_session: Session,
) -> None:
    """Verify a malformed format is a 422-level error like a malformed case_id."""
    with pytest.raises(ValidationException, match="format invalide"):
        ReportService(db_session).list_reports(
            case_id=uuid.uuid4(), internal=True, format="pdf"
        )


def test_update_report_structured_body_rejects_unvalidated_title(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify a proposed title inside a structured section body blocks the update."""
    draft = Report(
        case_id=setup["case"].id,
        format=ReportFormat.JSON.value,
        content="ancien contenu",
        sha256="0" * 64,
        status=ReportStatus.DRAFT.value,
        generation_id=str(uuid.uuid4()),
        version=4,
    )
    db_session.add(draft)
    db_session.commit()

    structured = _structured_content(setup["case"].id)
    structured = structured.model_copy(
        update={
            "sections": [
                section.model_copy(
                    update={"content": f"Analyse : {_PROPOSED_TITLE}."}
                    if section.key == "observations"
                    else {}
                )
                for section in structured.sections
            ]
        }
    )
    with pytest.raises(ReportGenerationFailedException, match="non validé"):
        ReportService(db_session).update_report(
            report_id=draft.id,
            content=structured,
            case_id=setup["case"].id,
            internal=True,
        )
    db_session.refresh(draft)
    assert draft.content == "ancien contenu"


class _EchoingAgent:
    """Agent double whose external draft echoes a pseudonymized rejection."""

    def __init__(self, content: ReportContent) -> None:
        self.content = content

    def generate_sync(self, context: Any, **kwargs: Any) -> ReportContent:
        """Return the prebuilt draft without running the agent's own guards."""
        return self.content


def test_external_seal_guard_rejects_pseudonymized_invalid_title(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify the service refuses to seal an echoed pseudonymized rejection."""
    case_id = setup["case"].id
    invalid_title = "Connexion non validée depuis 198.51.100.27"
    db_session.add(
        Finding(
            case_id=case_id,
            title=invalid_title,
            severity=FindingSeverity.HIGH,
            status=FindingStatus.PROPOSED,
        )
    )
    db_session.commit()

    pseudonymizer = DeterministicPseudonymizer()
    pseudonym = pseudonymizer.pseudonymize(invalid_title, case_id=str(case_id)).pseudonymized_text
    draft = _structured_content(case_id)
    draft = draft.model_copy(
        update={
            "sections": [
                section.model_copy(
                    update={"content": f"Voir {pseudonym}."}
                    if section.key == "observations"
                    else {}
                )
                for section in draft.sections
            ]
        }
    )

    with pytest.raises(ReportGenerationFailedException, match="non validé"):
        ReportService(db_session, agent=_EchoingAgent(draft)).generate_report(
            case_id=case_id,
            internal=True,
            h3_approved=True,
            pseudonymizer=pseudonymizer,
        )
    assert db_session.scalars(select(Report)).all() == []


def test_update_report_rejects_pseudonymized_invalid_title(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify the update path also excludes pseudonymized unvalidated titles."""
    case_id = setup["case"].id
    invalid_title = "Hypothèse non validée depuis 198.51.100.27"
    db_session.add(
        Finding(
            case_id=case_id,
            title=invalid_title,
            severity=FindingSeverity.HIGH,
            status=FindingStatus.PROPOSED,
        )
    )
    draft = Report(
        case_id=case_id,
        format=ReportFormat.MARKDOWN.value,
        content="ancien contenu",
        sha256="0" * 64,
        status=ReportStatus.DRAFT.value,
        generation_id=str(uuid.uuid4()),
        version=5,
    )
    db_session.add_all([draft])
    db_session.commit()

    pseudonymizer = DeterministicPseudonymizer()
    pseudonym = pseudonymizer.pseudonymize(invalid_title, case_id=str(case_id)).pseudonymized_text
    with pytest.raises(ReportGenerationFailedException, match="non validé"):
        ReportService(db_session).update_report(
            report_id=draft.id,
            content=f"Voir {pseudonym}.",
            case_id=case_id,
            internal=True,
            pseudonymizer=pseudonymizer,
        )
    db_session.refresh(draft)
    assert draft.content == "ancien contenu"


def test_update_report_accepts_pseudonymized_validated_title(
    db_session: Session,
    setup: dict[str, Any],
) -> None:
    """Verify a validated finding can be cited under its pseudonymized form."""
    case_id = setup["case"].id
    draft = Report(
        case_id=case_id,
        format=ReportFormat.MARKDOWN.value,
        content="ancien contenu",
        sha256="0" * 64,
        status=ReportStatus.DRAFT.value,
        generation_id=str(uuid.uuid4()),
        version=6,
    )
    db_session.add(draft)
    db_session.commit()

    pseudonymizer = DeterministicPseudonymizer()
    pseudonym = pseudonymizer.pseudonymize(
        _VALIDATED_TITLE, case_id=str(case_id)
    ).pseudonymized_text
    body = f"Voir {pseudonym}."
    updated = ReportService(db_session).update_report(
        report_id=draft.id,
        content=body,
        case_id=case_id,
        internal=True,
        pseudonymizer=pseudonymizer,
    )
    assert updated.content == body
    assert updated.sha256 == hashlib.sha256(body.encode("utf-8")).hexdigest()
