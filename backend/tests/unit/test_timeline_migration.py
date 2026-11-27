"""Unit tests for Alembic migration 008_create_observations_case_id_timestamp_utc_index."""

import importlib
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool


def _get_migration_008_module():
    """Dynamically import migration module 008."""
    return importlib.import_module(
        "migrations.versions.008_create_observations_case_id_timestamp_utc_index"
    )


def test_migration_008_metadata() -> None:
    """Verify revision 008 identifier and down_revision pointing to 007."""
    migration_008 = _get_migration_008_module()
    assert migration_008.revision == "008"
    assert migration_008.down_revision == "007"


def test_migration_008_offline_upgrade_sql() -> None:
    """Verify offline alembic upgrade produces valid DDL statements including 008."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline upgrade to head
    command.upgrade(cfg, "head", sql=True)

    script_dir = ScriptDirectory.from_config(cfg)
    assert script_dir.get_heads() == ["010"]

    revisions = [rev.revision for rev in script_dir.walk_revisions()]
    assert "008" in revisions


def test_migration_008_offline_downgrade_sql() -> None:
    """Verify offline alembic downgrade from 008 to 007 produces valid drop statements."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute offline downgrade from 008 to 007
    command.downgrade(cfg, "008:007", sql=True)


def test_migration_008_upgrade_and_downgrade_live_database() -> None:
    """Verify alembic upgrade to head (010) and downgrade to 007 and base."""
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

        # Run upgrade to head (010)
        command.upgrade(cfg, "head")

        inspector = inspect(connection)
        tables = inspector.get_table_names()
        assert "observations" in tables

        # Verify index ix_observations_case_id_timestamp_utc exists on observations
        indexes = inspector.get_indexes("observations")
        index_names = {idx["name"] for idx in indexes}
        assert "ix_observations_case_id_timestamp_utc" in index_names

        composite_idx = next(
            idx for idx in indexes if idx["name"] == "ix_observations_case_id_timestamp_utc"
        )
        assert composite_idx["column_names"] == ["case_id", "timestamp_utc"]

        # Run downgrade to 007
        command.downgrade(cfg, "007")

        inspector = inspect(connection)
        indexes_after_downgrade = inspector.get_indexes("observations")
        index_names_after = {idx["name"] for idx in indexes_after_downgrade}
        assert "ix_observations_case_id_timestamp_utc" not in index_names_after

        # Re-upgrade to head (010)
        command.upgrade(cfg, "head")
        inspector_re = inspect(connection)
        indexes_re = inspector_re.get_indexes("observations")
        assert "ix_observations_case_id_timestamp_utc" in {idx["name"] for idx in indexes_re}
