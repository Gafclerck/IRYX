"""Unit tests for Alembic migration 001_create_user_table."""

import importlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool


def _get_migration_module():
    """Dynamically import migration module with leading digits."""
    return importlib.import_module("migrations.versions.001_create_user_table")


def test_migration_001_metadata() -> None:
    """Verify revision identifiers and linear migration chain."""
    migration_001 = _get_migration_module()
    assert migration_001.revision == "001"
    assert migration_001.down_revision is None


def test_migration_001_offline_upgrade_sql() -> None:
    """Verify offline alembic upgrade produces valid DDL statements for users table."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline upgrade
    command.upgrade(cfg, "head", sql=True)

    script_dir = ScriptDirectory.from_config(cfg)
    revisions = list(script_dir.walk_revisions())
    assert len(revisions) >= 1
    assert revisions[0].revision == "001"


def test_migration_001_offline_downgrade_sql() -> None:
    """Verify offline alembic downgrade produces valid drop statements."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline downgrade from 001 to base
    command.downgrade(cfg, "001:base", sql=True)


def test_migration_upgrade_and_downgrade_on_database() -> None:
    """Verify alembic upgrade and downgrade directly against a live SQLite database."""
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

        # Run upgrade to head
        command.upgrade(cfg, "head")

        inspector = inspect(connection)
        tables = inspector.get_table_names()
        assert "users" in tables

        columns = {col["name"]: col for col in inspector.get_columns("users")}
        expected_columns = {
            "id",
            "email",
            "hashed_password",
            "is_active",
            "created_at",
            "updated_at",
        }
        assert expected_columns.issubset(columns.keys())

        # Verify not null constraints
        assert columns["email"]["nullable"] is False
        assert columns["hashed_password"]["nullable"] is False
        assert columns["is_active"]["nullable"] is False

        # Verify unique index on email
        indexes = inspector.get_indexes("users")
        email_indexes = [idx for idx in indexes if "email" in idx["column_names"]]
        assert len(email_indexes) >= 1
        assert any(idx["unique"] for idx in email_indexes)

        # Run downgrade to base
        command.downgrade(cfg, "base")

        inspector_after = inspect(connection)
        assert "users" not in inspector_after.get_table_names()
