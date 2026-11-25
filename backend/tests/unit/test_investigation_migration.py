"""Unit tests for Alembic migration 006_create_investigation_and_phase_tables."""

import importlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool


def _get_migration_006_module():
    """Dynamically import migration module 006."""
    return importlib.import_module("migrations.versions.006_create_investigation_and_phase_tables")


def test_migration_006_metadata() -> None:
    """Verify revision 006 identifier and down_revision pointing to 005."""
    migration_006 = _get_migration_006_module()
    assert migration_006.revision == "006"
    assert migration_006.down_revision == "005"


def test_migration_006_offline_upgrade_sql() -> None:
    """Verify offline alembic upgrade produces valid DDL statements including 006."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline upgrade to head
    command.upgrade(cfg, "head", sql=True)

    script_dir = ScriptDirectory.from_config(cfg)
    assert script_dir.get_heads() == ["006"]

    revisions = [rev.revision for rev in script_dir.walk_revisions()]
    assert "006" in revisions


def test_migration_006_offline_downgrade_sql() -> None:
    """Verify offline alembic downgrade from 006 to 005 produces valid drop statements."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline downgrade from 006 to 005
    command.downgrade(cfg, "006:005", sql=True)


def test_migration_006_upgrade_and_downgrade_live_database() -> None:
    """Verify alembic upgrade to head (006) and downgrade to 005, 004, and base."""
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

        # Run upgrade to head (006)
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

        # Verify investigation_runs columns
        run_columns = {col["name"]: col for col in inspector.get_columns("investigation_runs")}
        expected_run_cols = {
            "id",
            "case_id",
            "status",
            "current_phase",
            "validated_plan",
            "iteration_count",
            "error_count",
            "started_at",
            "updated_at",
        }
        assert expected_run_cols.issubset(run_columns.keys())
        assert run_columns["id"]["nullable"] is False
        assert run_columns["case_id"]["nullable"] is False
        assert run_columns["status"]["nullable"] is False
        assert run_columns["current_phase"]["nullable"] is False
        assert run_columns["iteration_count"]["nullable"] is False
        assert run_columns["error_count"]["nullable"] is False
        assert run_columns["started_at"]["nullable"] is False
        assert run_columns["updated_at"]["nullable"] is False
        assert run_columns["validated_plan"]["nullable"] is True

        # Verify phases columns
        phase_columns = {col["name"]: col for col in inspector.get_columns("phases")}
        expected_phase_cols = {
            "id",
            "investigation_run_id",
            "phase_name",
            "status",
            "started_at",
            "completed_at",
        }
        assert expected_phase_cols.issubset(phase_columns.keys())
        assert phase_columns["id"]["nullable"] is False
        assert phase_columns["investigation_run_id"]["nullable"] is False
        assert phase_columns["phase_name"]["nullable"] is False
        assert phase_columns["status"]["nullable"] is False
        assert phase_columns["started_at"]["nullable"] is False
        assert phase_columns["completed_at"]["nullable"] is True

        # Verify foreign keys
        run_fks = inspector.get_foreign_keys("investigation_runs")
        assert any(fk["referred_table"] == "cases" for fk in run_fks)

        phase_fks = inspector.get_foreign_keys("phases")
        assert any(fk["referred_table"] == "investigation_runs" for fk in phase_fks)

        # Downgrade to 005
        command.downgrade(cfg, "005")
        inspector_005 = inspect(connection)
        tables_005 = inspector_005.get_table_names()
        assert "investigation_runs" not in tables_005
        assert "phases" not in tables_005
        assert "tool_executions" in tables_005
        assert "cases" in tables_005

        # Downgrade to base
        command.downgrade(cfg, "base")
        inspector_base = inspect(connection)
        assert len(inspector_base.get_table_names()) == 1  # alembic_version only
