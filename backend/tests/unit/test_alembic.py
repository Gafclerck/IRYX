"""Tests for Alembic migration configuration and audit of create_all prohibition."""

import configparser
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from iryx.db.base import POSTGRES_NAMING_CONVENTION, Base


def test_production_code_strictly_forbids_create_all():
    """Rule 9 & Spec Constraint: No invocation of Base.metadata.create_all in production code."""
    backend_src_dir = Path(__file__).resolve().parent.parent.parent / "src" / "iryx"
    assert backend_src_dir.is_dir()

    violating_files: list[str] = []
    for py_file in backend_src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "create_all" in content:
            violating_files.append(str(py_file))

    assert violating_files == [], (
        f"Base.metadata.create_all() found in production code: {violating_files}"
    )


def test_declarative_base_naming_convention():
    """Verify that Base.metadata has the required deterministic naming conventions."""
    assert Base.metadata.naming_convention is not None
    convention = Base.metadata.naming_convention

    required_keys = {"ix", "uq", "ck", "fk", "pk"}
    assert required_keys.issubset(convention.keys())

    assert convention["ix"] == POSTGRES_NAMING_CONVENTION["ix"]
    assert convention["uq"] == POSTGRES_NAMING_CONVENTION["uq"]
    assert convention["ck"] == POSTGRES_NAMING_CONVENTION["ck"]
    assert convention["fk"] == POSTGRES_NAMING_CONVENTION["fk"]
    assert convention["pk"] == POSTGRES_NAMING_CONVENTION["pk"]


def test_alembic_ini_backend_configuration():
    """Verify backend/alembic.ini structure, script_location, and version_locations."""
    ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    assert ini_path.is_file(), f"File not found: {ini_path}"

    parser = configparser.ConfigParser(interpolation=None)
    parser.read(ini_path, encoding="utf-8")

    assert parser.has_section("alembic")
    script_loc = parser.get("alembic", "script_location")
    assert "migrations" in script_loc

    version_loc = parser.get("alembic", "version_locations")
    assert "versions" in version_loc


def test_alembic_root_ini_configuration():
    """Verify root alembic.ini points to backend/migrations."""
    root_ini = Path(__file__).resolve().parent.parent.parent.parent / "alembic.ini"
    assert root_ini.is_file(), f"File not found: {root_ini}"

    parser = configparser.ConfigParser(interpolation=None)
    parser.read(root_ini, encoding="utf-8")

    assert parser.has_section("alembic")
    script_loc = parser.get("alembic", "script_location")
    assert "backend/migrations" in script_loc or "backend" in script_loc


def test_alembic_script_directory_initial_state():
    """Verify Alembic can inspect the migration directory and reports a single unique head."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    # Override script location to absolute path for the test runner
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    script_dir = ScriptDirectory.from_config(cfg)
    heads = script_dir.get_heads()
    assert len(heads) == 1
    assert heads[0] is not None


def test_alembic_offline_upgrade_execution():
    """Verify alembic upgrade head in offline mode executes env.py and binds metadata."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Execute upgrade head in offline mode (sql=True)
    command.upgrade(cfg, "head", sql=True)
