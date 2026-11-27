"""Unit tests for the append-only audit service (Story 8.5)."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from iryx.audit.models import AuditEvent
from iryx.audit.services import AuditService, compute_audit_payload_hash, sanitize_details
from iryx.auth.models import Membership, MembershipRole, Organization, User
from iryx.cases.models import Case


def _canonical_digest(payload: dict[str, Any]) -> str:
    """Return the lowercase SHA-256 hex digest of a canonical JSON payload."""
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest().lower()


def test_compute_audit_payload_hash_is_deterministic() -> None:
    """Verify the SHA-256 audit digest of a canonical action payload."""
    target_id = uuid.uuid4()
    details = {"status": "open"}
    first = compute_audit_payload_hash("CASE_READ", "Case", target_id, details)
    second = compute_audit_payload_hash("CASE_READ", "Case", target_id, details)

    assert first == second
    assert first == _canonical_digest(
        {
            "action": "CASE_READ",
            "target_type": "Case",
            "target_id": str(target_id),
            "details": details,
        }
    )
    assert len(first) == 64
    assert first == first.lower()
    assert first != compute_audit_payload_hash("CASE_READ", "Case", uuid.uuid4(), details)
    assert first != compute_audit_payload_hash("CASE_WRITE", "Case", target_id, details)
    assert first != compute_audit_payload_hash("CASE_READ", "Finding", target_id, details)


def test_compute_audit_payload_hash_defaults_to_empty_details() -> None:
    """Verify anonymous actions hash the same canonical payload with empty details."""
    target_id = uuid.uuid4()
    digest = compute_audit_payload_hash("AUTH_LOGIN", "User", target_id, None)

    assert digest == _canonical_digest(
        {
            "action": "AUTH_LOGIN",
            "target_type": "User",
            "target_id": str(target_id),
            "details": {},
        }
    )


def test_sanitize_details_strips_secret_keys_recursively() -> None:
    """Verify secret-bearing keys are removed at any depth, values never persisted."""
    sanitized = sanitize_details(
        {
            "password": "super-secret",
            "api_key": "key-123",
            "nested": {"token": "jwt-token", "keep": "value"},
            "list": [{"secret": "hidden", "ok": "fine"}],
        }
    )

    assert sanitized == {"nested": {"keep": "value"}, "list": [{"ok": "fine"}]}


def test_audit_service_record_flushes_without_commit_and_caller_commits(
    db_session: Session,
) -> None:
    """Verify the audit write stays in the caller transaction and commits on demand."""
    org = Organization(name="Audit Service Org")
    user = User(email=f"audit-svc-{uuid.uuid4()}@cert.fr", hashed_password="pw")
    db_session.add_all([org, user])
    db_session.flush()
    db_session.add(
        Membership(
            organization_id=org.id,
            user_id=user.id,
            role=MembershipRole.INVESTIGATOR,
        )
    )
    db_session.flush()
    case = Case(
        organization_id=org.id,
        title="Dossier audit",
        created_by=user.id,
    )
    db_session.add(case)
    db_session.flush()
    db_session.commit()

    audit_service = AuditService(db_session)
    record_kwargs: dict[str, Any] = {
        "action": "CASE_CREATE",
        "actor_id": user.id,
        "case_id": case.id,
        "target_type": "Case",
        "target_id": case.id,
        "details": {"title": "Dossier audit"},
    }

    # Recording only flushes: a rollback discards the uncommitted audit write.
    audit_service.record(**record_kwargs)
    db_session.rollback()
    assert db_session.scalar(select(AuditEvent)) is None

    event = audit_service.record(**record_kwargs)
    assert event.id is not None
    assert event.payload_hash == event.payload_hash.lower()
    assert event.details == {"title": "Dossier audit"}

    db_session.commit()
    recorded = db_session.scalar(select(AuditEvent))
    assert recorded is not None
    assert recorded.action == "CASE_CREATE"
    assert recorded.actor_id == user.id


def test_audit_service_record_uses_system_actor_for_anonymous_actions(db_session: Session) -> None:
    """Verify anonymous actions persist a null actor id and a system marker."""
    user = User(email=f"audit-anon-{uuid.uuid4()}@cert.fr", hashed_password="pw")
    db_session.add(user)
    db_session.flush()
    db_session.commit()

    audit_service = AuditService(db_session)
    event = audit_service.record(
        action="AUTH_LOGIN",
        actor_id=None,
        case_id=None,
        target_type="User",
        target_id=user.id,
        details={"method": "password"},
    )

    assert event.actor_id is None
    assert event.details["actor"] == "system"
    assert event.details["method"] == "password"


def test_audit_service_record_sanitizes_secrets_before_storing(db_session: Session) -> None:
    """Verify password or token fragments never reach the persisted details."""
    org = Organization(name="Audit Sanitize Org")
    user = User(email=f"audit-sanitize-{uuid.uuid4()}@cert.fr", hashed_password="pw")
    db_session.add_all([org, user])
    db_session.flush()
    db_session.commit()

    audit_service = AuditService(db_session)
    event = audit_service.record(
        action="EVIDENCE_UPLOAD",
        actor_id=user.id,
        case_id=None,
        target_type="Evidence",
        target_id=uuid.uuid4(),
        details={"original_name": "auth.log", "password": "hunter2"},
    )

    assert "password" not in event.details
    assert event.details["original_name"] == "auth.log"
    assert event.payload_hash == event.payload_hash.lower()


def test_audit_service_lists_case_events_in_chronological_order(
    db_session: Session,
) -> None:
    """Verify listing is oldest-first and honours limit/offset pagination."""
    case_id = uuid.uuid4()
    for index in range(3):
        db_session.add(
            AuditEvent(
                id=uuid.uuid4(),
                case_id=case_id,
                actor_id=None,
                action="GATE_H1_DECISION",
                target_type="InvestigationRun",
                target_id=uuid.uuid4(),
                payload_hash="a" * 64,
                details={"index": index},
                created_at=datetime(2026, 11, 26, 9, 0, index, tzinfo=UTC),
            )
        )
    db_session.commit()

    audit_service = AuditService(db_session)
    page = audit_service.list_events(case_id=case_id, limit=2, offset=0)
    assert len(page) == 2
    assert [event.details["index"] for event in page] == [0, 1]

    last_page = audit_service.list_events(case_id=case_id, limit=2, offset=2)
    assert len(last_page) == 1
    assert last_page[0].details["index"] == 2

    assert audit_service.count_events(case_id=case_id) == 3


def test_finding_review_emits_finding_review_audit(db_session: Session) -> None:
    """Verify human-in-the-loop finding review writes one FINDING_REVIEW row."""
    from iryx.analytics.models import (
        Finding,
        FindingConfidence,
        FindingSeverity,
        FindingStatus,
        FindingType,
    )
    from iryx.analytics.schemas import FindingReview
    from iryx.analytics.services import FindingService

    org = Organization(name="Audit Finding Org")
    user = User(email=f"audit-finding-{uuid.uuid4()}@cert.fr", hashed_password="pw")
    db_session.add_all([org, user])
    db_session.flush()
    case = Case(organization_id=org.id, title="Dossier revue", created_by=user.id)
    db_session.add(case)
    db_session.flush()
    finding = Finding(
        case_id=case.id,
        title="Connexion suspecte",
        severity=FindingSeverity.HIGH,
        confidence=FindingConfidence.HIGH,
        finding_type=FindingType.FACT,
        status=FindingStatus.PROPOSED,
    )
    db_session.add(finding)
    db_session.commit()

    FindingService(db_session).review_finding(
        case_id=case.id,
        finding_id=finding.id,
        payload=FindingReview(action="validate"),
        user_id=user.id,
    )

    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "FINDING_REVIEW")
    ).all()
    assert len(events) == 1
    assert events[0].target_type == "Finding"
    assert events[0].target_id == finding.id
    assert events[0].case_id == case.id


def test_audit_events_are_append_only_on_sqlite(db_session: Session) -> None:
    """Verify the SQLite trigger rejects UPDATE and DELETE on audit rows."""
    event = AuditEvent(
        id=uuid.uuid4(),
        case_id=None,
        actor_id=None,
        action="CASE_READ",
        target_type="Case",
        target_id=uuid.uuid4(),
        payload_hash="b" * 64,
        details={},
        created_at=datetime.now(UTC),
    )
    db_session.add(event)
    db_session.commit()

    db_session.expire_all()
    stored = db_session.scalar(select(AuditEvent))
    assert stored is not None

    stored.action = "CASE_WRITE"
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    db_session.expire_all()
    stored = db_session.scalar(select(AuditEvent))
    assert stored is not None
    with pytest.raises(IntegrityError):
        db_session.delete(stored)
        db_session.flush()
    db_session.rollback()
