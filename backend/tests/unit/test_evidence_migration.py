"""Unit tests for Alembic migration 004_create_evidence_and_ingestion_tables."""

import importlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool


def _get_migration_004_module():
    """Dynamically import migration module 004."""
    return importlib.import_module("migrations.versions.004_create_evidence_and_ingestion_tables")


def test_migration_004_metadata() -> None:
    """Verify revision 004 identifier and down_revision pointing to 003."""
    migration_004 = _get_migration_004_module()
    assert migration_004.revision == "004"
    assert migration_004.down_revision == "003"


def test_migration_004_offline_upgrade_sql() -> None:
    """Verify offline alembic upgrade produces valid DDL statements including 004."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline upgrade to head
    command.upgrade(cfg, "head", sql=True)

    script_dir = ScriptDirectory.from_config(cfg)
    revisions = [rev.revision for rev in script_dir.walk_revisions()]
    assert "004" in revisions


def test_migration_004_offline_downgrade_sql() -> None:
    """Verify offline alembic downgrade from 004 to 003 produces valid drop statements."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline downgrade from 004 to 003
    command.downgrade(cfg, "004:003", sql=True)


def test_migration_004_upgrade_and_downgrade_live_database() -> None:
    """Verify alembic upgrade to head (004) and downgrade to 003, 002, 001 and base."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    with engine.connect() as connection:
        cfg = Config(str(ini_path))
        cfg.set_main_option("script_location", str(backend_dir / "migrations"))
        cfg.attributes["connection"] = connection

        # Run upgrade to head (004)
        command.upgrade(cfg, "head")

        inspector = inspect(connection)
        tables = inspector.get_table_names()
        assert "users" in tables
        assert "organizations" in tables
        assert "memberships" in tables
        assert "cases" in tables
        assert "evidences" in tables
        assert "ingestion_runs" in tables

        # Verify evidences columns
        evidence_columns = {col["name"]: col for col in inspector.get_columns("evidences")}
        expected_evidence_cols = {
            "id",
            "case_id",
            "original_name",
            "file_size",
            "sha256",
            "detected_type",
            "imported_by",
            "created_at",
        }
        assert expected_evidence_cols.issubset(evidence_columns.keys())
        assert evidence_columns["id"]["nullable"] is False
        assert evidence_columns["case_id"]["nullable"] is False
        assert evidence_columns["original_name"]["nullable"] is False
        assert evidence_columns["file_size"]["nullable"] is False
        assert evidence_columns["created_at"]["nullable"] is False
        assert evidence_columns["sha256"]["nullable"] is True
        assert evidence_columns["detected_type"]["nullable"] is True
        assert evidence_columns["imported_by"]["nullable"] is True

        # Verify foreign keys on evidences
        evidence_fks = inspector.get_foreign_keys("evidences")
        evidence_fk_tables = {fk["referred_table"] for fk in evidence_fks}
        assert "cases" in evidence_fk_tables
        assert "users" in evidence_fk_tables

        # Verify indexes on evidences
        evidence_indexes = inspector.get_indexes("evidences")
        evidence_indexed_cols = {col for idx in evidence_indexes for col in idx["column_names"]}
        assert "case_id" in evidence_indexed_cols
        assert "imported_by" in evidence_indexed_cols
        assert "sha256" in evidence_indexed_cols
        assert "created_at" in evidence_indexed_cols

        # Verify ingestion_runs columns
        run_columns = {col["name"]: col for col in inspector.get_columns("ingestion_runs")}
        expected_run_cols = {
            "id",
            "evidence_id",
            "status",
            "progress",
            "error_message",
            "started_at",
            "completed_at",
        }
        assert expected_run_cols.issubset(run_columns.keys())
        assert run_columns["id"]["nullable"] is False
        assert run_columns["evidence_id"]["nullable"] is False
        assert run_columns["status"]["nullable"] is False
        assert run_columns["progress"]["nullable"] is False
        assert run_columns["started_at"]["nullable"] is False
        assert run_columns["error_message"]["nullable"] is True
        assert run_columns["completed_at"]["nullable"] is True

        # Verify foreign keys on ingestion_runs
        run_fks = inspector.get_foreign_keys("ingestion_runs")
        run_fk_tables = {fk["referred_table"] for fk in run_fks}
        assert "evidences" in run_fk_tables

        # Verify indexes on ingestion_runs
        run_indexes = inspector.get_indexes("ingestion_runs")
        run_indexed_cols = {col for idx in run_indexes for col in idx["column_names"]}
        assert "evidence_id" in run_indexed_cols
        assert "status" in run_indexed_cols

        # Downgrade to 003
        command.downgrade(cfg, "003")
        inspector_003 = inspect(connection)
        tables_003 = inspector_003.get_table_names()
        assert "ingestion_runs" not in tables_003
        assert "evidences" not in tables_003
        assert "cases" in tables_003
        assert "memberships" in tables_003
        assert "organizations" in tables_003
        assert "users" in tables_003

        # Downgrade to 002
        command.downgrade(cfg, "002")
        inspector_002 = inspect(connection)
        tables_002 = inspector_002.get_table_names()
        assert "cases" not in tables_002
        assert "memberships" in tables_002
        assert "organizations" in tables_002
        assert "users" in tables_002

        # Downgrade to base
        command.downgrade(cfg, "base")
        inspector_base = inspect(connection)
        assert "users" not in inspector_base.get_table_names()
        assert "evidences" not in inspector_base.get_table_names()
