"""Unit tests for Alembic migration 002_create_org_and_membership_tables."""

import importlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool


def _get_migration_002_module():
    """Dynamically import migration module with leading digits."""
    return importlib.import_module(
        "migrations.versions.002_create_org_and_membership_tables"
    )


def test_migration_002_metadata() -> None:
    """Verify revision 002 identifier and down_revision pointing to 001."""
    migration_002 = _get_migration_002_module()
    assert migration_002.revision == "002"
    assert migration_002.down_revision == "001"


def test_migration_002_offline_upgrade_sql() -> None:
    """Verify offline alembic upgrade produces valid DDL statements including 002."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline upgrade
    command.upgrade(cfg, "head", sql=True)

    script_dir = ScriptDirectory.from_config(cfg)
    heads = script_dir.get_heads()
    assert heads == ["002"]


def test_migration_002_offline_downgrade_sql() -> None:
    """Verify offline alembic downgrade from 002 to 001 produces valid drop statements."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline downgrade from 002 to 001
    command.downgrade(cfg, "002:001", sql=True)


def test_migration_002_upgrade_and_downgrade_live_database() -> None:
    """Verify alembic upgrade to head and downgrade to 001 and base against SQLite."""
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

        # Run upgrade to head (002)
        command.upgrade(cfg, "head")

        inspector = inspect(connection)
        tables = inspector.get_table_names()
        assert "users" in tables
        assert "organizations" in tables
        assert "memberships" in tables

        # Verify organizations columns
        org_columns = {col["name"]: col for col in inspector.get_columns("organizations")}
        assert {"id", "name", "created_at", "updated_at"}.issubset(org_columns.keys())
        assert org_columns["name"]["nullable"] is False

        # Verify memberships columns
        membership_columns = {
            col["name"]: col for col in inspector.get_columns("memberships")
        }
        assert {"id", "organization_id", "user_id", "role", "created_at"}.issubset(
            membership_columns.keys()
        )
        assert membership_columns["organization_id"]["nullable"] is False
        assert membership_columns["user_id"]["nullable"] is False
        assert membership_columns["role"]["nullable"] is False

        # Verify foreign keys on memberships
        fks = inspector.get_foreign_keys("memberships")
        referred_tables = {fk["referred_table"] for fk in fks}
        assert "organizations" in referred_tables
        assert "users" in referred_tables

        # Verify unique constraint or index on (organization_id, user_id)
        unique_constraints = inspector.get_unique_constraints("memberships")
        indexes = inspector.get_indexes("memberships")
        composite_unique_found = any(
            set(uc["column_names"]) == {"organization_id", "user_id"}
            for uc in unique_constraints
        ) or any(
            idx["unique"] and set(idx["column_names"]) == {"organization_id", "user_id"}
            for idx in indexes
        )
        assert composite_unique_found, "Composite unique constraint/index missing on memberships."

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
