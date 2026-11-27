"""Emission tests verifying sensitive actions write exactly one audit event (Story 8.5)."""

import io
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi import UploadFile
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from iryx.audit.models import AuditEvent
from iryx.auth.models import Organization, User
from iryx.cases.models import Case
from iryx.core.config import Settings
from iryx.evidence.models import Evidence
from iryx.evidence.services import EvidenceService
from iryx.orchestrator.models import (
    InvestigationRun,
    InvestigationStatus,
    Phase,
    PhaseName,
    PhaseStatus,
)
from iryx.orchestrator.schemas import (
    H1DecisionRequest,
    H2Decision,
    H2DecisionRequest,
    H3Decision,
    H3DecisionRequest,
)
from iryx.orchestrator.services import InvestigationService, build_investigation_graph


def _org_and_user(db_session: Session, label: str) -> tuple[Organization, User]:
    org = Organization(name=f"Audit {label} Org")
    user = User(email=f"audit-{label}-{uuid.uuid4()}@cert.fr", hashed_password="pw")
    db_session.add_all([org, user])
    db_session.flush()
    return org, user


@pytest.mark.asyncio
async def test_evidence_upload_emits_evidence_upload_audit(db_session: Session, tmp_path) -> None:
    """Verify an accepted evidence upload writes one EVIDENCE_UPLOAD row atomically."""
    org, user = _org_and_user(db_session, "evidence")
    case = Case(organization_id=org.id, title="Dossier preuve", created_by=user.id)
    db_session.add(case)
    db_session.flush()
    db_session.commit()

    settings = Settings(
        secret_key="unit-test-secret-key-min-32-chars-long",
        evidence_storage_path=str(tmp_path.parent),
        evidence_staging_path=str(tmp_path),
        max_evidence_size_gb=1,
    )
    upload = UploadFile(
        file=io.BytesIO(b"evidence-bytes"),
        filename="auth.log",
        headers=Headers({"content-type": "application/octet-stream"}),
    )

    with (
        patch("iryx.evidence.services.get_settings", return_value=settings),
        patch("iryx.evidence.services.process_evidence_ingestion.delay"),
    ):
        service = EvidenceService(db_session)
        evidence, _ = await service.upload_evidence(
            case_id=case.id,
            file=upload,
            current_user_id=user.id,
        )

    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "EVIDENCE_UPLOAD")
    ).all()
    assert len(events) == 1
    assert events[0].target_type == "Evidence"
    assert events[0].target_id == evidence.id
    assert events[0].case_id == case.id
    assert events[0].actor_id == user.id
    assert events[0].details["original_name"] == "auth.log"


def test_gate_h1_decision_emits_gate_audit(db_session: Session) -> None:
    """Verify H1 arbitration writes one GATE_H1_DECISION row before commit."""
    org, user = _org_and_user(db_session, "gate")
    case = Case(organization_id=org.id, title="Dossier porte", created_by=user.id)
    db_session.add(case)
    db_session.flush()

    now = datetime.now(UTC)
    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.PAUSED,
        current_phase=PhaseName.WAITING_H1,
        validated_plan={"summary": "Plan", "steps": []},
        iteration_count=0,
        error_count=0,
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        Phase(
            id=uuid.uuid4(),
            investigation_run_id=run.id,
            phase_name=PhaseName.GATE_H1,
            status=PhaseStatus.ACTIVE,
            started_at=now,
        )
    )
    db_session.commit()

    InvestigationService(db_session).arbitrate_gate_h1(
        case_id=case.id,
        run_id=run.id,
        decision_request=H1DecisionRequest(decision="approve"),
        user_id=user.id,
    )

    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "GATE_H1_DECISION")
    ).all()
    assert len(events) == 1
    assert events[0].target_type == "InvestigationRun"
    assert events[0].target_id == run.id
    assert events[0].case_id == case.id
    assert events[0].actor_id == user.id
    assert events[0].details["decision"] == "approve"


def _paused_run_at(
    db_session: Session,
    case: Case,
    phase_name: PhaseName,
) -> InvestigationRun:
    """Create a run paused at the requested human gate."""
    now = datetime.now(UTC)
    run = InvestigationRun(
        id=uuid.uuid4(),
        case_id=case.id,
        status=InvestigationStatus.PAUSED,
        current_phase=phase_name,
        validated_plan={"summary": "Plan", "steps": []},
        iteration_count=0,
        error_count=0,
        started_at=now,
        updated_at=now,
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        Phase(
            id=uuid.uuid4(),
            investigation_run_id=run.id,
            phase_name=phase_name,
            status=PhaseStatus.ACTIVE,
            started_at=now,
        )
    )
    db_session.commit()
    return run


def test_gate_h2_decision_emits_gate_audit(db_session: Session) -> None:
    """Verify H2 arbitration writes one GATE_H2_DECISION row before commit."""
    org, user = _org_and_user(db_session, "gate-h2")
    case = Case(organization_id=org.id, title="Dossier porte H2", created_by=user.id)
    db_session.add(case)
    db_session.flush()
    run = _paused_run_at(db_session, case, PhaseName.WAITING_H2)

    InvestigationService(db_session).arbitrate_gate_h2(
        case_id=case.id,
        run_id=run.id,
        decision_request=H2DecisionRequest(decision=H2Decision.PROCEED),
        user_id=user.id,
    )

    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "GATE_H2_DECISION")
    ).all()
    assert len(events) == 1
    assert events[0].target_type == "InvestigationRun"
    assert events[0].target_id == run.id
    assert events[0].case_id == case.id
    assert events[0].actor_id == user.id
    assert events[0].details["decision"] == "proceed"


def test_gate_h3_decision_emits_gate_audit(db_session: Session) -> None:
    """Verify H3 arbitration writes one GATE_H3_DECISION row before commit."""
    org, user = _org_and_user(db_session, "gate-h3")
    case = Case(organization_id=org.id, title="Dossier porte H3", created_by=user.id)
    db_session.add(case)
    db_session.flush()
    run = _paused_run_at(db_session, case, PhaseName.WAITING_H3)

    InvestigationService(db_session, checkpointer=MemorySaver()).arbitrate_gate_h3(
        case_id=case.id,
        run_id=run.id,
        decision_request=H3DecisionRequest(
            decision=H3Decision.REJECT,
            feedback="Gabarit local impose",
        ),
        user_id=user.id,
    )

    events = db_session.scalars(
        select(AuditEvent).where(AuditEvent.action == "GATE_H3_DECISION")
    ).all()
    assert len(events) == 1
    assert events[0].target_type == "InvestigationRun"
    assert events[0].target_id == run.id
    assert events[0].case_id == case.id
    assert events[0].actor_id == user.id
    assert events[0].details["decision"] == "reject"
    assert events[0].details["approved"] is False


@pytest.mark.asyncio
async def test_evidence_upload_rolls_back_when_audit_fails(
    db_session: Session,
    tmp_path,
) -> None:
    """Verify an audit failure rolls back the evidence row (fail-closed)."""
    org, user = _org_and_user(db_session, "evidence-fail")
    case = Case(organization_id=org.id, title="Dossier preuve", created_by=user.id)
    db_session.add(case)
    db_session.commit()

    settings = Settings(
        secret_key="unit-test-secret-key-min-32-chars-long",
        evidence_storage_path=str(tmp_path.parent),
        evidence_staging_path=str(tmp_path),
        max_evidence_size_gb=1,
    )
    upload = UploadFile(
        file=io.BytesIO(b"evidence-bytes"),
        filename="auth.log",
        headers=Headers({"content-type": "application/octet-stream"}),
    )

    with (
        patch("iryx.evidence.services.get_settings", return_value=settings),
        patch("iryx.evidence.services.process_evidence_ingestion.delay"),
        patch(
            "iryx.evidence.services.AuditService.record",
            side_effect=RuntimeError("audit down"),
        ),
        pytest.raises(RuntimeError, match="audit down"),
    ):
        await EvidenceService(db_session).upload_evidence(
            case_id=case.id,
            file=upload,
            current_user_id=user.id,
        )

    assert list(db_session.scalars(select(Evidence)).all()) == []
    assert list(db_session.scalars(select(AuditEvent)).all()) == []


def test_gate_h2_rolls_back_when_audit_fails(db_session: Session) -> None:
    """Verify an audit failure leaves the H2 run untouched once rolled back."""
    org, user = _org_and_user(db_session, "gate-h2-fail")
    case = Case(organization_id=org.id, title="Dossier porte H2", created_by=user.id)
    db_session.add(case)
    db_session.flush()
    run = _paused_run_at(db_session, case, PhaseName.WAITING_H2)

    with (
        patch(
            "iryx.orchestrator.services.AuditService.record",
            side_effect=RuntimeError("audit down"),
        ),
        pytest.raises(RuntimeError, match="audit down"),
    ):
        InvestigationService(db_session).arbitrate_gate_h2(
            case_id=case.id,
            run_id=run.id,
            decision_request=H2DecisionRequest(decision=H2Decision.PROCEED),
            user_id=user.id,
        )

    db_session.rollback()
    db_session.refresh(run)
    assert run.status == InvestigationStatus.PAUSED
    assert run.current_phase == PhaseName.WAITING_H2
    assert list(db_session.scalars(select(AuditEvent)).all()) == []


def test_gate_h3_audit_failure_leaves_checkpointer_undecided(db_session: Session) -> None:
    """Verify an H3 audit failure rolls back both the DB and the checkpointer verdict."""
    org, user = _org_and_user(db_session, "gate-h3-fail")
    case = Case(organization_id=org.id, title="Dossier porte H3", created_by=user.id)
    db_session.add(case)
    db_session.flush()
    run = _paused_run_at(db_session, case, PhaseName.WAITING_H3)

    checkpointer = MemorySaver()
    service = InvestigationService(db_session, checkpointer=checkpointer)

    with (
        patch(
            "iryx.orchestrator.services.AuditService.record",
            side_effect=RuntimeError("audit down"),
        ),
        pytest.raises(RuntimeError, match="audit down"),
    ):
        service.arbitrate_gate_h3(
            case_id=case.id,
            run_id=run.id,
            decision_request=H3DecisionRequest(decision=H3Decision.APPROVE),
            user_id=user.id,
        )

    db_session.rollback()
    db_session.refresh(run)
    assert run.status == InvestigationStatus.PAUSED
    assert run.current_phase == PhaseName.WAITING_H3
    assert list(db_session.scalars(select(AuditEvent)).all()) == []

    snapshot = build_investigation_graph(checkpointer=checkpointer).get_state(
        {"configurable": {"thread_id": str(run.id)}}
    )
    assert snapshot.values.get("h3_approved") is not True
    assert snapshot.values.get("h3_rejected") is not True
