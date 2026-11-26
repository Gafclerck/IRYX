"""Unit tests for Alembic migration 007_create_finding_table."""

import importlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool


def _get_migration_007_module():
    """Dynamically import migration module 007."""
    return importlib.import_module("migrations.versions.007_create_finding_table")


def test_migration_007_metadata() -> None:
    """Verify revision 007 identifier and down_revision pointing to 006."""
    migration_007 = _get_migration_007_module()
    assert migration_007.revision == "007"
    assert migration_007.down_revision == "006"


def test_migration_007_offline_upgrade_sql() -> None:
    """Verify offline alembic upgrade produces valid DDL statements including 007."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline upgrade to head
    command.upgrade(cfg, "head", sql=True)

    script_dir = ScriptDirectory.from_config(cfg)
    assert script_dir.get_heads() == ["009"]

    revisions = [rev.revision for rev in script_dir.walk_revisions()]
    assert "007" in revisions


def test_migration_007_offline_downgrade_sql() -> None:
    """Verify offline alembic downgrade from 007 to 006 produces valid drop statements."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline downgrade from 007 to 006
    command.downgrade(cfg, "007:006", sql=True)


def test_migration_007_upgrade_and_downgrade_live_database() -> None:
    """Verify alembic upgrade to head (007) and downgrade to 006 and base."""
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

        # Run upgrade to head (007)
        command.upgrade(cfg, "head")

        inspector = inspect(connection)
        tables = inspector.get_table_names()
        assert "users" in tables
        assert "organizations" in tables
        assert "memberships" in tables
        assert "cases" in tables
        assert "evidences" in tables
        assert "ingestion_runs" in tables
        assert "tool_executions" in tables
        assert "observations" in tables
        assert "investigation_runs" in tables
        assert "phases" in tables
        assert "findings" in tables

        # Verify findings columns
        finding_columns = {col["name"]: col for col in inspector.get_columns("findings")}
        expected_cols = {
            "id",
            "case_id",
            "title",
            "severity",
            "confidence",
            "finding_type",
            "status",
            "observation_refs",
            "tool_execution_refs",
            "created_by",
            "created_at",
        }
        assert expected_cols.issubset(finding_columns.keys())
        assert finding_columns["id"]["nullable"] is False
        assert finding_columns["case_id"]["nullable"] is False
        assert finding_columns["title"]["nullable"] is False
        assert finding_columns["severity"]["nullable"] is False
        assert finding_columns["confidence"]["nullable"] is False
        assert finding_columns["finding_type"]["nullable"] is False
        assert finding_columns["status"]["nullable"] is False
        assert finding_columns["observation_refs"]["nullable"] is False
        assert finding_columns["tool_execution_refs"]["nullable"] is False
        assert finding_columns["created_by"]["nullable"] is True
        assert finding_columns["created_at"]["nullable"] is False

        # Verify indexes
        indexes = {idx["name"]: idx for idx in inspector.get_indexes("findings")}
        assert "ix_findings_case_id" in indexes
        assert "ix_findings_status" in indexes
        assert "ix_findings_severity" in indexes
        assert "ix_findings_created_by" in indexes
        assert "ix_findings_created_at" in indexes

        # Downgrade to 006
        command.downgrade(cfg, "006")
        inspector_006 = inspect(connection)
        tables_006 = inspector_006.get_table_names()
        assert "findings" not in tables_006
        assert "investigation_runs" in tables_006
        assert "phases" in tables_006

        # Re-upgrade to head (007)
        command.upgrade(cfg, "head")
        inspector_re = inspect(connection)
        assert "findings" in inspector_re.get_table_names()
