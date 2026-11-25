"""Unit tests for Alembic migration 005_create_tool_execution_and_observation_tables."""

import importlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool


def _get_migration_005_module():
    """Dynamically import migration module 005."""
    return importlib.import_module(
        "migrations.versions.005_create_tool_execution_and_observation_tables"
    )


def test_migration_005_metadata() -> None:
    """Verify revision 005 identifier and down_revision pointing to 004."""
    migration_005 = _get_migration_005_module()
    assert migration_005.revision == "005"
    assert migration_005.down_revision == "004"


def test_migration_005_offline_upgrade_sql() -> None:
    """Verify offline alembic upgrade produces valid DDL statements including 005."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline upgrade to head
    command.upgrade(cfg, "head", sql=True)

    script_dir = ScriptDirectory.from_config(cfg)
    revisions = [rev.revision for rev in script_dir.walk_revisions()]
    assert "005" in revisions


def test_migration_005_offline_downgrade_sql() -> None:
    """Verify offline alembic downgrade from 005 to 004 produces valid drop statements."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline downgrade from 005 to 004
    command.downgrade(cfg, "005:004", sql=True)


def test_migration_005_upgrade_and_downgrade_live_database() -> None:
    """Verify alembic upgrade to head (005) and downgrade to 004, 003, and base."""
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

        # Run upgrade to head (005)
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

        # Verify tool_executions columns
        tool_columns = {col["name"]: col for col in inspector.get_columns("tool_executions")}
        expected_tool_cols = {
            "id",
            "case_id",
            "tool_name",
            "tool_version",
            "agent_role",
            "parameters",
            "result_sha256",
            "duration_ms",
            "status",
            "error_message",
            "created_at",
        }
        assert expected_tool_cols.issubset(tool_columns.keys())
        assert tool_columns["id"]["nullable"] is False
        assert tool_columns["case_id"]["nullable"] is False
        assert tool_columns["tool_name"]["nullable"] is False
        assert tool_columns["tool_version"]["nullable"] is False
        assert tool_columns["agent_role"]["nullable"] is False
        assert tool_columns["parameters"]["nullable"] is False
        assert tool_columns["duration_ms"]["nullable"] is False
        assert tool_columns["status"]["nullable"] is False
        assert tool_columns["created_at"]["nullable"] is False
        assert tool_columns["result_sha256"]["nullable"] is True
        assert tool_columns["error_message"]["nullable"] is True

        # Verify observations columns
        obs_columns = {col["name"]: col for col in inspector.get_columns("observations")}
        expected_obs_cols = {
            "id",
            "case_id",
            "source_id",
            "tool_name",
            "tool_execution_id",
            "normalized_content",
            "timestamp_utc",
            "source_location",
            "created_at",
        }
        assert expected_obs_cols.issubset(obs_columns.keys())
        assert obs_columns["id"]["nullable"] is False
        assert obs_columns["case_id"]["nullable"] is False
        assert obs_columns["tool_name"]["nullable"] is False
        assert obs_columns["normalized_content"]["nullable"] is False
        assert obs_columns["created_at"]["nullable"] is False
        assert obs_columns["source_id"]["nullable"] is True
        assert obs_columns["tool_execution_id"]["nullable"] is True
        assert obs_columns["timestamp_utc"]["nullable"] is True
        assert obs_columns["source_location"]["nullable"] is True

        # Verify foreign keys
        tool_fks = inspector.get_foreign_keys("tool_executions")
        assert any(fk["referred_table"] == "cases" for fk in tool_fks)

        obs_fks = inspector.get_foreign_keys("observations")
        fk_tables = {fk["referred_table"] for fk in obs_fks}
        assert "cases" in fk_tables
        assert "evidences" in fk_tables
        assert "tool_executions" in fk_tables

        # Downgrade to 004
        command.downgrade(cfg, "004")
        inspector_004 = inspect(connection)
        tables_004 = inspector_004.get_table_names()
        assert "tool_executions" not in tables_004
        assert "observations" not in tables_004
        assert "evidences" in tables_004
        assert "cases" in tables_004

        # Downgrade to base
        command.downgrade(cfg, "base")
        inspector_base = inspect(connection)
        assert len(inspector_base.get_table_names()) == 1  # alembic_version only
