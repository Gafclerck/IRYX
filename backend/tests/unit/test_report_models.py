"""Unit tests for Report and AuditEvent ORM models (Story 8.3)."""

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from iryx.audit.models import AuditEvent
from iryx.auth.models import Organization, User
from iryx.cases.models import Case
from iryx.db.base import Base
from iryx.reporting.models import Report
from iryx.reporting.schemas import ReportFormat, ReportStatus

_SHA256 = "a" * 64


@pytest.fixture
def case_row(db_session: Session) -> Case:
    """Create a minimal organization, user and case for report rows."""
    import iryx.analytics.models  # noqa: F401
    import iryx.audit.models  # noqa: F401
    import iryx.evidence.models  # noqa: F401
    import iryx.gateway.models  # noqa: F401
    import iryx.orchestrator.models  # noqa: F401
    import iryx.reporting.models  # noqa: F401

    org = Organization(name="Report ORM Unit")
    user = User(email=f"report-orm-{uuid.uuid4()}@cert.fr", hashed_password="pw")
    db_session.add_all([org, user])
    db_session.flush()
    case = Case(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Dossier ORM",
        description="Contexte du dossier",
        created_by=user.id,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    return case


def _report(case: Case, **overrides: Any) -> Report:
    """Build a valid Report row with optional overrides."""
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "case_id": case.id,
        "format": ReportFormat.MARKDOWN.value,
        "content": "contenu scellé",
        "sha256": _SHA256,
        "status": ReportStatus.VALIDATED.value,
        "generation_id": str(uuid.uuid4()),
        "version": 1,
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    return Report(**values)


def test_report_defaults_and_repr_do_not_expose_content(
    db_session: Session,
    case_row: Case,
) -> None:
    """Verify defaults are materialized and repr never leaks report content."""
    row = Report(
        case_id=case_row.id,
        format=ReportFormat.MARKDOWN.value,
        content="contenu confidentiel",
        sha256=_SHA256,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    assert row.status == ReportStatus.DRAFT.value
    assert row.version == 1
    assert row.created_at is not None
    assert len(row.generation_id) == 36
    assert "confidentiel" not in repr(row)
    assert "contenu" not in repr(row)


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"format": "pdf"}, "ck_reports_format_check"),
        ({"status": "exported_pending"}, "ck_reports_status_check"),
        ({"content": ""}, "ck_reports_content_check"),
        ({"version": 0}, "ck_reports_version_check"),
        ({"sha256": "A" * 64}, "ck_reports_sha256_hex_check"),
        ({"sha256": "a" * 63}, "ck_reports_sha256_hex_check"),
    ],
)
def test_report_constraints_reject_invalid_rows(
    db_session: Session,
    case_row: Case,
    overrides: dict[str, Any],
    constraint: str,
) -> None:
    """Verify every CHECK constraint is enforced under its exact metadata name."""
    db_session.add(_report(case_row, **overrides))
    with pytest.raises(IntegrityError) as exc_info:
        db_session.commit()
    assert constraint in str(exc_info.value.orig)
    db_session.rollback()


def test_report_unique_version_per_format(
    db_session: Session,
    case_row: Case,
) -> None:
    """Verify (case_id, version, format) uniqueness while allowing both formats."""
    generation_id = str(uuid.uuid4())
    db_session.add(_report(case_row, generation_id=generation_id))
    db_session.add(
        _report(case_row, format=ReportFormat.JSON.value, generation_id=generation_id)
    )
    db_session.commit()

    db_session.add(_report(case_row, generation_id=str(uuid.uuid4())))
    with pytest.raises(IntegrityError) as exc_info:
        db_session.commit()
    # SQLite reports the column list rather than the named constraint, so assert
    # both the reported columns and the exact name registered in the metadata.
    assert "UNIQUE constraint failed: reports.case_id, reports.version, reports.format" in str(
        exc_info.value.orig
    )
    names = {
        item["name"]
        for item in inspect(db_session.get_bind()).get_unique_constraints("reports")
    }
    assert "uq_reports_case_version_format" in names
    db_session.rollback()

    assert len(db_session.scalars(select(Report).where(Report.case_id == case_row.id)).all()) == 2


def test_report_fk_cascades_and_audit_fks_restrict() -> None:
    """Verify real deletes: reports cascade with their case, audit rows block deletion."""
    import iryx.analytics.models  # noqa: F401
    import iryx.audit.models  # noqa: F401
    import iryx.cases.models  # noqa: F401
    import iryx.evidence.models  # noqa: F401
    import iryx.gateway.models  # noqa: F401
    import iryx.orchestrator.models  # noqa: F401
    import iryx.reporting.models  # noqa: F401

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        org = Organization(name="Constraint Org")
        user = User(email=f"constraint-{uuid.uuid4()}@cert.fr", hashed_password="pw")
        session.add_all([org, user])
        session.flush()
        case = Case(
            id=uuid.uuid4(),
            organization_id=org.id,
            title="Contraintes",
            created_by=user.id,
        )
        session.add(case)
        session.flush()
        session.add(
            Report(
                case_id=case.id,
                format="markdown",
                content="contenu",
                sha256=_SHA256,
                generation_id=str(uuid.uuid4()),
                version=1,
            )
        )
        session.commit()

        session.delete(case)
        session.commit()
        assert session.scalars(select(Report)).all() == []

        other_case = Case(
            id=uuid.uuid4(), organization_id=org.id, title="Piste", created_by=user.id
        )
        session.add(other_case)
        session.flush()
        session.add(
            AuditEvent(
                case_id=other_case.id,
                actor_id=user.id,
                event_type="report.generated",
                payload={"ok": True},
                payload_sha256=_SHA256,
            )
        )
        session.commit()

        with pytest.raises(IntegrityError):
            session.delete(other_case)
            session.commit()
        session.rollback()
        assert session.scalars(select(AuditEvent)).all() != []

        with pytest.raises(IntegrityError) as exc_info:
            session.delete(user)
            session.commit()
        # SQLite hides the FK name in the error, so verify it from the DDL.
        assert "FOREIGN KEY constraint failed" in str(exc_info.value.orig)
        fk_names = {item["name"] for item in inspect(engine).get_foreign_keys("audit_events")}
        assert "fk_audit_events_actor_id_users" in fk_names
        session.rollback()
    engine.dispose()
