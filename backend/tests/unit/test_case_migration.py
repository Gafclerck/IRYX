"""Unit tests for Alembic migration 003_create_case_table."""

import importlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool


def _get_migration_003_module():
    """Dynamically import migration module 003."""
    return importlib.import_module("migrations.versions.003_create_case_table")


def test_migration_003_metadata() -> None:
    """Verify revision 003 identifier and down_revision pointing to 002."""
    migration_003 = _get_migration_003_module()
    assert migration_003.revision == "003"
    assert migration_003.down_revision == "002"


def test_migration_003_offline_upgrade_sql() -> None:
    """Verify offline alembic upgrade produces valid DDL statements including 003."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline upgrade
    command.upgrade(cfg, "head", sql=True)

    script_dir = ScriptDirectory.from_config(cfg)
    revisions = [rev.revision for rev in script_dir.walk_revisions()]
    assert "003" in revisions


def test_migration_003_offline_downgrade_sql() -> None:
    """Verify offline alembic downgrade from 003 to 002 produces valid drop statements."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline downgrade from 003 to 002
    command.downgrade(cfg, "003:002", sql=True)


def test_migration_003_upgrade_and_downgrade_live_database() -> None:
    """Verify alembic upgrade to head and downgrade to 002, 001 and base against SQLite."""
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

        # Run upgrade to head (003)
        command.upgrade(cfg, "head")

        inspector = inspect(connection)
        tables = inspector.get_table_names()
        assert "users" in tables
        assert "organizations" in tables
        assert "memberships" in tables
        assert "cases" in tables

        # Verify cases columns
        case_columns = {col["name"]: col for col in inspector.get_columns("cases")}
        expected_cols = {
            "id",
            "organization_id",
            "title",
            "description",
            "status",
            "created_by",
            "created_at",
            "updated_at",
        }
        assert expected_cols.issubset(case_columns.keys())

        # Verify nullability
        assert case_columns["id"]["nullable"] is False
        assert case_columns["organization_id"]["nullable"] is False
        assert case_columns["title"]["nullable"] is False
        assert case_columns["status"]["nullable"] is False
        assert case_columns["created_at"]["nullable"] is False
        assert case_columns["updated_at"]["nullable"] is False
        assert case_columns["description"]["nullable"] is True
        assert case_columns["created_by"]["nullable"] is True

        # Verify foreign keys on cases
        fks = inspector.get_foreign_keys("cases")
        referred_tables = {fk["referred_table"] for fk in fks}
        assert "organizations" in referred_tables
        assert "users" in referred_tables

        # Verify indexes on cases
        indexes = inspector.get_indexes("cases")
        indexed_cols = {col for idx in indexes for col in idx["column_names"]}
        assert "organization_id" in indexed_cols
        assert "created_by" in indexed_cols
        assert "status" in indexed_cols

        # Downgrade to 002
        command.downgrade(cfg, "002")
        inspector_002 = inspect(connection)
        tables_002 = inspector_002.get_table_names()
        assert "cases" not in tables_002
        assert "memberships" in tables_002
        assert "organizations" in tables_002
        assert "users" in tables_002

        # Downgrade to 001
        command.downgrade(cfg, "001")
        inspector_001 = inspect(connection)
        tables_001 = inspector_001.get_table_names()
        assert "memberships" not in tables_001
        assert "organizations" not in tables_001
        assert "users" in tables_001

        # Downgrade to base
        command.downgrade(cfg, "base")
        inspector_base = inspect(connection)
        assert "users" not in inspector_base.get_table_names()
