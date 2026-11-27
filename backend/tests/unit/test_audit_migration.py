"""Unit tests for Alembic migration 010_finalize_audit_events (Story 8.5)."""

import importlib
import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _config() -> Config:
    """Build an Alembic configuration rooted at the backend directory."""
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
    return cfg


def test_migration_010_metadata_and_single_head() -> None:
    """Verify revision 010 follows 009 and is the only head."""
    migration = importlib.import_module("migrations.versions.010_finalize_audit_events")
    assert migration.revision == "010"
    assert migration.down_revision == "009"

    script_dir = ScriptDirectory.from_config(_config())
    assert script_dir.get_heads() == ["010"]


def test_migration_010_offline_upgrade_sql_contains_final_audit_shape() -> None:
    """Capture offline PostgreSQL DDL and assert the finalized audit table."""
    cfg = _config()
    buffer = io.StringIO()
    cfg.output_buffer = buffer
    command.upgrade(cfg, "head", sql=True)
    sql = buffer.getvalue()

    assert "CREATE TABLE audit_events" in sql
    assert "action VARCHAR(128) NOT NULL" in sql
    assert "target_type VARCHAR(64) NOT NULL" in sql
    assert "details JSONB NOT NULL" in sql
    assert "CONSTRAINT ck_audit_events_action_check CHECK (length(action) > 0)" in sql
    assert (
        "CONSTRAINT ck_audit_events_payload_hash_hex_check CHECK "
        "(payload_hash ~ '^[0-9a-f]{64}$')" in sql
    )
    assert "ON DELETE RESTRICT" in sql
    assert "CREATE OR REPLACE FUNCTION prevent_audit_event_mutation" in sql
    assert "CREATE TRIGGER trg_audit_events_append_only" in sql
    assert "BEFORE UPDATE OR DELETE ON audit_events" in sql


def test_migration_010_upgrade_and_downgrade_live_database() -> None:
    """Verify live upgrade produces the new audit shape and downgrade restores 009."""
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
        audit_columns = {col["name"]: col for col in inspector.get_columns("audit_events")}
        assert {
            "id",
            "case_id",
            "actor_id",
            "action",
            "target_type",
            "target_id",
            "payload_hash",
            "details",
            "created_at",
        }.issubset(audit_columns)
        assert audit_columns["case_id"]["nullable"] is True
        assert audit_columns["actor_id"]["nullable"] is True
        assert audit_columns["target_id"]["nullable"] is False

        audit_checks = {check["name"] for check in inspector.get_check_constraints("audit_events")}
        assert "ck_audit_events_action_check" in audit_checks
        assert "ck_audit_events_payload_hash_hex_check" in audit_checks

        command.downgrade(cfg, "009")
        inspector_009 = inspect(connection)
        audit_columns_009 = {col["name"] for col in inspector_009.get_columns("audit_events")}
        assert "event_type" in audit_columns_009
        assert "payload_sha256" in audit_columns_009
        assert "action" not in audit_columns_009


def test_migration_010_installs_effective_append_only_trigger() -> None:
    """Verify inserted audit rows cannot subsequently be updated or deleted."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        cfg = _config()
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "head")

        connection.execute(
            text(
                "INSERT INTO audit_events "
                "(id, case_id, actor_id, action, target_type, target_id, payload_hash, details) "
                "VALUES ('audit-event-id', NULL, NULL, 'CASE_READ', 'Case', "
                "'target-id', :digest, '{}')"
            ),
            {"digest": "c" * 64},
        )
        connection.commit()

        with pytest.raises(IntegrityError):
            connection.execute(text("UPDATE audit_events SET action = 'CASE_WRITE'"))
        connection.rollback()

        with pytest.raises(IntegrityError):
            connection.execute(text("DELETE FROM audit_events"))
        connection.rollback()
