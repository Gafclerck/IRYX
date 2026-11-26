"""Unit tests for Alembic migration 009_create_report_and_audit_tables (Story 8.3)."""

import importlib
import io
import uuid
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from iryx.audit.models import AuditEvent
from iryx.db.base import Base
from iryx.reporting.models import Report

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _config() -> Config:
    """Build an Alembic configuration rooted at the backend directory."""
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
    return cfg


def _migration_009() -> object:
    """Dynamically import migration module 009."""
    return importlib.import_module("migrations.versions.009_create_report_and_audit_tables")


def test_migration_009_metadata_and_single_head() -> None:
    """Verify revision 009 follows 008 and is the only head."""
    migration = _migration_009()
    assert migration.revision == "009"  # type: ignore[attr-defined]
    assert migration.down_revision == "008"  # type: ignore[attr-defined]

    script_dir = ScriptDirectory.from_config(_config())
    assert script_dir.get_heads() == ["009"]


def test_migration_009_offline_upgrade_sql_contains_both_hex_checks() -> None:
    """Capture offline PostgreSQL DDL and assert both SHA-256 checks use a regex."""
    cfg = _config()
    buffer = io.StringIO()
    cfg.output_buffer = buffer
    command.upgrade(cfg, "head", sql=True)
    sql = buffer.getvalue()

    assert "CREATE TABLE reports" in sql
    assert "CREATE TABLE audit_events" in sql
    assert "ck_reports_sha256_hex_check CHECK (sha256 ~ '^[0-9a-f]{64}$')" in sql
    assert (
        "ck_audit_events_payload_sha256_hex_check CHECK "
        "(payload_sha256 ~ '^[0-9a-f]{64}$')"
    ) in sql
    assert sql.count("^[0-9a-f]{64}$") == 2
    assert "payload JSONB NOT NULL" in sql
    assert "uq_reports_case_version_format UNIQUE (case_id, version, format)" in sql
    assert "ON DELETE RESTRICT" in sql
    assert (
        "CONSTRAINT fk_reports_case_id_cases FOREIGN KEY(case_id) "
        "REFERENCES cases (id) ON DELETE CASCADE" in sql
    )
    assert "GLOB" not in sql


def test_migration_009_offline_downgrade_sql() -> None:
    """Verify offline downgrade from 009 to 008 produces mirror drop statements."""
    cfg = _config()
    buffer = io.StringIO()
    cfg.output_buffer = buffer
    command.downgrade(cfg, "009:008", sql=True)
    sql = buffer.getvalue()

    assert "DROP INDEX ix_audit_events_case_id_created_at" in sql
    assert "DROP TABLE audit_events" in sql
    assert "DROP INDEX ix_reports_case_id_format" in sql
    assert "DROP TABLE reports" in sql


def test_migration_009_upgrade_and_downgrade_live_database() -> None:
    """Verify live upgrade creates constrained tables and downgrade removes both."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        cfg = _config()
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")

        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        assert {"reports", "audit_events"}.issubset(tables)

        report_columns = {col["name"]: col for col in inspector.get_columns("reports")}
        assert {
            "id",
            "case_id",
            "format",
            "content",
            "sha256",
            "status",
            "generation_id",
            "version",
            "created_at",
        }.issubset(report_columns)
        assert report_columns["content"]["nullable"] is False
        assert report_columns["sha256"]["nullable"] is False

        checks = {
            check["name"]: check["sqltext"]
            for check in inspector.get_check_constraints("reports")
        }
        assert "ck_reports_format_check" in checks
        assert "ck_reports_status_check" in checks
        assert "ck_reports_content_check" in checks
        assert "ck_reports_version_check" in checks
        assert "ck_reports_sha256_hex_check" in checks
        assert "[0-9a-f]" in checks["ck_reports_sha256_hex_check"]

        audit_checks = {
            check["name"]: check["sqltext"]
            for check in inspector.get_check_constraints("audit_events")
        }
        assert "ck_audit_events_payload_sha256_hex_check" in audit_checks

        uniques = {uq["name"]: uq for uq in inspector.get_unique_constraints("reports")}
        unique = next(iter(uniques.values()))
        assert set(unique["column_names"]) == {"case_id", "version", "format"}

        report_indexes = {idx["name"] for idx in inspector.get_indexes("reports")}
        assert {
            "ix_reports_case_id",
            "ix_reports_format",
            "ix_reports_sha256",
            "ix_reports_status",
            "ix_reports_generation_id",
            "ix_reports_case_id_format",
        }.issubset(report_indexes)
        audit_indexes = {idx["name"] for idx in inspector.get_indexes("audit_events")}
        assert "ix_audit_events_case_id_created_at" in audit_indexes

        command.downgrade(cfg, "008")
        inspector_008 = inspect(connection)
        assert "reports" not in inspector_008.get_table_names()
        assert "audit_events" not in inspector_008.get_table_names()
        assert "findings" in inspector_008.get_table_names()


def test_report_sha256_hex_check_rejects_invalid_digests() -> None:
    """Verify the SQLite CHECK blocks malformed hashes and accepts lowercase hex."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        cfg = _config()
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
        now = datetime.now(UTC).isoformat()
        base = (
            "INSERT INTO reports "
            "(id, case_id, format, content, sha256, status, generation_id, version, created_at) "
            "VALUES ('{rid}', '{cid}', 'markdown', 'contenu', '{digest}', 'validated', "
            "'{generation}', 1, '{now}')"
        )
        case_id = str(uuid.uuid4())
        connection.execute(
            text(
                "INSERT INTO cases (id, organization_id, title, description, status, "
                "created_by, created_at, updated_at) "
                "VALUES (:cid, :oid, 'titre', 'description', 'open', NULL, :now, :now)"
            ),
            {"cid": case_id, "oid": str(uuid.uuid4()), "now": now},
        )

        connection.execute(
            text(
                base.format(
                    rid=str(uuid.uuid4()),
                    cid=case_id,
                    digest="a" * 64,
                    generation=str(uuid.uuid4()),
                    now=now,
                )
            )
        )
        for invalid in ("A" * 64, "a" * 63, "g" * 64):
            try:
                connection.execute(
                    text(
                        base.format(
                            rid=str(uuid.uuid4()),
                            cid=case_id,
                            digest=invalid,
                            generation=str(uuid.uuid4()),
                            now=now,
                        )
                    )
                )
            except Exception:
                connection.rollback()
            else:
                connection.rollback()
                raise AssertionError(f"CHECK should reject digest {invalid!r}")


def test_audit_events_payload_sha256_hex_check_rejects_invalid_digest() -> None:
    """Verify the SQLite CHECK rejects malformed audit digests (regex on PostgreSQL)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        cfg = _config()
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
        now = datetime.now(UTC).isoformat()
        case_id = str(uuid.uuid4())
        actor_id = str(uuid.uuid4())
        connection.execute(
            text(
                "INSERT INTO users (id, email, hashed_password, created_at, updated_at) "
                "VALUES (:uid, :email, 'pw', :now, :now)"
            ),
            {"uid": actor_id, "email": f"audit-{actor_id}@cert.fr", "now": now},
        )
        connection.execute(
            text(
                "INSERT INTO cases (id, organization_id, title, description, status, "
                "created_by, created_at, updated_at) "
                "VALUES (:cid, :oid, 'titre', 'description', 'open', NULL, :now, :now)"
            ),
            {"cid": case_id, "oid": str(uuid.uuid4()), "now": now},
        )
        base = (
            "INSERT INTO audit_events "
            "(id, case_id, actor_id, event_type, payload, payload_sha256, created_at) "
            "VALUES ('{aid}', '{cid}', '{uid}', 'report_generated', '{{}}', "
            "'{digest}', '{now}')"
        )
        connection.execute(
            text(
                base.format(
                    aid=str(uuid.uuid4()),
                    cid=case_id,
                    uid=actor_id,
                    digest="a" * 64,
                    now=now,
                )
            )
        )
        connection.commit()

        for invalid in ("A" * 64, "a" * 63, "g" * 64):
            try:
                connection.execute(
                    text(
                        base.format(
                            aid=str(uuid.uuid4()),
                            cid=case_id,
                            uid=actor_id,
                            digest=invalid,
                            now=now,
                        )
                    )
                )
            except Exception:
                connection.rollback()
            else:
                connection.rollback()
                raise AssertionError(f"CHECK should reject payload digest {invalid!r}")


def test_orm_hex_checks_compile_for_both_dialects() -> None:
    """Verify ORM metadata compiles a regex on PostgreSQL and a GLOB on SQLite."""
    pg_ddl = str(CreateTable(Report.__table__).compile(dialect=postgresql.dialect()))
    sqlite_ddl = str(CreateTable(Report.__table__).compile(dialect=sqlite.dialect()))

    assert "sha256 ~ '^[0-9a-f]{64}$'" in pg_ddl
    assert "payload_sha256 ~ '^[0-9a-f]{64}$'" in str(
        CreateTable(AuditEvent.__table__).compile(dialect=postgresql.dialect())
    )
    assert "sha256 GLOB '" + "[0-9a-f]" * 64 + "'" in sqlite_ddl
    assert "GLOB" not in pg_ddl
    assert "~ '" not in sqlite_ddl


def test_migration_009_has_no_autogenerate_drift_for_new_tables() -> None:
    """Verify migration 009 and ORM metadata agree on the two new tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        cfg = _config()
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")
        diffs = compare_metadata(MigrationContext.configure(connection), Base.metadata)
        relevant = [
            diff
            for diff in diffs
            if "reports" in repr(diff) or "audit_events" in repr(diff)
        ]
        assert relevant == []
    engine.dispose()
