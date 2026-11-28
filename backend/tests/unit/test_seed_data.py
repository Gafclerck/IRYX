"""Unit tests for the idempotent demo seed script (Story 9.3)."""

import contextlib
import hashlib
import os
import stat
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.auth.models import Membership, MembershipRole, Organization, User
from iryx.cases.models import Case, CaseStatus
from iryx.core.config import Settings
from iryx.core.security import verify_password
from iryx.db.base import Base
from iryx.evidence.models import Evidence, IngestionRun, IngestionStatus
from iryx.gateway.base import ToolExecutionContext
from iryx.gateway.tools.evtx_parser import EvtxParserParameters, EvtxParserTool
from iryx.gateway.tools.prefetch_parser import PrefetchParserParameters, PrefetchParserTool
from iryx.scripts import seed_data


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory, resetting read-only files before cleanup."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        path = Path(tmp)
        yield path
        for file in path.rglob("*"):
            if file.is_file():
                with contextlib.suppress(OSError):
                    os.chmod(file, stat.S_IWRITE | stat.S_IREAD)


@pytest.fixture
def session_factory() -> Generator[sessionmaker[Session], None, None]:
    """Provide an isolated in-memory SQLite session factory."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def settings(temp_dir: Path) -> Settings:
    """Provide settings pointing at a temporary evidence staging directory."""
    return Settings(
        secret_key="unit-test-secret-key-min-32-chars-long",
        evidence_storage_path=str(temp_dir),
        evidence_staging_path=str(temp_dir / "staging"),
        max_evidence_size_gb=1,
    )


@pytest.fixture
def patched_seed(
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> Generator[None, None, None]:
    """Route both the seed and the ingestion task to the test database/settings."""
    with (
        patch("iryx.scripts.seed_data.SessionLocal", side_effect=session_factory),
        patch("iryx.scripts.seed_data.get_settings", return_value=settings),
        patch("iryx.evidence.tasks.SessionLocal", side_effect=session_factory),
        patch("iryx.evidence.tasks.get_settings", return_value=settings),
    ):
        yield


def _count(session_factory: sessionmaker[Session], model: type[Base]) -> int:
    with session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _staging_path(settings: Settings, evidence: Evidence) -> Path:
    return Path(settings.evidence_staging_path) / f"{evidence.id}.bin"


def _latest_run(session: Session, evidence_id: uuid.UUID) -> IngestionRun | None:
    return session.scalar(
        select(IngestionRun)
        .where(IngestionRun.evidence_id == evidence_id)
        .order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc())
    )


def test_seed_demo_data_nominal(
    patched_seed: None,
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    summary = seed_data.seed_demo_data()

    assert summary.organization_name == seed_data.ORGANIZATION_NAME
    assert summary.case_title == seed_data.CASE_TITLE
    assert len(summary.evidences) == 3
    assert {item.original_name for item in summary.evidences} == {
        "Security.evtx",
        "POWERSHELL.EXE-DEMO1234.pf",
        "MEMORY.DMP",
    }

    with session_factory() as session:
        organization = session.scalar(
            select(Organization).where(Organization.name == seed_data.ORGANIZATION_NAME)
        )
        assert organization is not None

        users = {user.email: user for user in session.scalars(select(User)).all()}
        assert set(users) == {spec.email for spec in seed_data.DEMO_USERS}

        memberships = {
            membership.user_id: membership
            for membership in session.scalars(select(Membership)).all()
        }
        for spec in seed_data.DEMO_USERS:
            user = users[spec.email]
            assert user.is_active is True
            assert user.hashed_password.startswith("$argon2id$")
            assert verify_password(spec.password, user.hashed_password) is True
            assert memberships[user.id].organization_id == organization.id
            assert memberships[user.id].role == spec.role.value

        case = session.scalar(select(Case).where(Case.title == seed_data.CASE_TITLE))
        assert case is not None
        assert case.organization_id == organization.id
        assert case.status == CaseStatus.OPEN

        evidences = session.scalars(select(Evidence).where(Evidence.case_id == case.id)).all()
        assert len(evidences) == 3
        for evidence in evidences:
            assert evidence.file_size > 0
            assert evidence.sha256 is not None
            assert evidence.detected_type is not None
            path = _staging_path(settings, evidence)
            assert path.is_file()
            assert path.stat().st_size == evidence.file_size
            assert hashlib.sha256(path.read_bytes()).hexdigest() == evidence.sha256
            # Sealed files must not be writable (0o440 on POSIX, read-only on Windows).
            assert stat.S_IMODE(path.stat().st_mode) & 0o222 == 0

            run = _latest_run(session, evidence.id)
            assert run is not None
            assert run.status == IngestionStatus.COMPLETED
            assert run.progress == 100
            assert run.error_message is None
            assert run.completed_at is not None


def test_seed_is_idempotent_on_second_run(
    patched_seed: None,
    session_factory: sessionmaker[Session],
) -> None:
    first = seed_data.seed_demo_data()
    second = seed_data.seed_demo_data()

    assert first.case_id == second.case_id
    assert _count(session_factory, Organization) == 1
    assert _count(session_factory, User) == 4
    assert _count(session_factory, Membership) == 4
    assert _count(session_factory, Case) == 1
    assert _count(session_factory, Evidence) == 3
    assert _count(session_factory, IngestionRun) == 3

    with session_factory() as session:
        for evidence in session.scalars(select(Evidence)).all():
            assert evidence.sha256 is not None
            run = _latest_run(session, evidence.id)
            assert run is not None
            assert run.status == IngestionStatus.COMPLETED


def test_seed_repairs_invalid_demo_password(
    patched_seed: None,
    session_factory: sessionmaker[Session],
) -> None:
    seed_data.seed_demo_data()

    with session_factory() as session:
        admin = session.scalar(select(User).where(User.email == "admin@iryx.local"))
        assert admin is not None
        admin.hashed_password = "not-a-valid-argon2-hash"
        session.commit()

    seed_data.seed_demo_data()

    with session_factory() as session:
        admin = session.scalar(select(User).where(User.email == "admin@iryx.local"))
        assert admin is not None
        assert admin.hashed_password.startswith("$argon2id$")
        assert verify_password("Admin12345!", admin.hashed_password) is True
    assert _count(session_factory, User) == 4


def test_seed_restores_missing_staging_file(
    patched_seed: None,
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    seed_data.seed_demo_data()

    with session_factory() as session:
        evidence = session.scalar(select(Evidence).where(Evidence.original_name == "Security.evtx"))
        assert evidence is not None
        evidence_id = evidence.id
        expected_sha256 = evidence.sha256
    path = Path(settings.evidence_staging_path) / f"{evidence_id}.bin"
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    path.unlink()

    seed_data.seed_demo_data()

    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256
    with session_factory() as session:
        evidence = session.get(Evidence, evidence_id)
        assert evidence is not None
        assert evidence.sha256 == expected_sha256
        run = _latest_run(session, evidence_id)
        assert run is not None
        assert run.status == IngestionStatus.COMPLETED


def test_seed_reseals_partially_sealed_evidence(
    patched_seed: None,
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    seed_data.seed_demo_data()

    with session_factory() as session:
        evidence = session.scalar(
            select(Evidence).where(Evidence.original_name == "POWERSHELL.EXE-DEMO1234.pf")
        )
        assert evidence is not None
        evidence_id = evidence.id
        evidence.sha256 = None
        evidence.detected_type = None
        run = _latest_run(session, evidence_id)
        assert run is not None
        run.status = IngestionStatus.PENDING
        run.progress = 0
        session.commit()

    seed_data.seed_demo_data()

    with session_factory() as session:
        evidence = session.get(Evidence, evidence_id)
        assert evidence is not None
        assert evidence.sha256 is not None
        assert evidence.detected_type is not None
        run = _latest_run(session, evidence_id)
        assert run is not None
        assert run.status == IngestionStatus.COMPLETED
        assert run.progress == 100
    path = Path(settings.evidence_staging_path) / f"{evidence_id}.bin"
    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == evidence.sha256


def test_seed_repairs_completed_run_with_progress_below_100(
    patched_seed: None,
    session_factory: sessionmaker[Session],
) -> None:
    seed_data.seed_demo_data()

    with session_factory() as session:
        evidence = session.scalar(select(Evidence).where(Evidence.original_name == "Security.evtx"))
        assert evidence is not None
        evidence_id = evidence.id
        run = _latest_run(session, evidence_id)
        assert run is not None
        run.progress = 50
        session.commit()

    seed_data.seed_demo_data()

    with session_factory() as session:
        run = _latest_run(session, evidence_id)
        assert run is not None
        assert run.status == IngestionStatus.COMPLETED
        assert run.progress == 100


async def test_seeded_evtx_contains_4624_and_4688(
    patched_seed: None,
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    seed_data.seed_demo_data()

    with session_factory() as session:
        evidence = session.scalar(select(Evidence).where(Evidence.original_name == "Security.evtx"))
        assert evidence is not None
        path = _staging_path(settings, evidence)

    result = await EvtxParserTool().execute(
        EvtxParserParameters(file_path=str(path)),
        ToolExecutionContext(case_id=uuid.uuid4()),
    )

    assert result.status == "success"
    event_ids = {str(event["event_id"]) for event in result.raw_output["events"]}
    assert {"4624", "4688"} <= event_ids


async def test_seeded_prefetch_is_parsed_by_prefetch_parser_tool(
    patched_seed: None,
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    seed_data.seed_demo_data()

    with session_factory() as session:
        evidence = session.scalar(
            select(Evidence).where(Evidence.original_name == "POWERSHELL.EXE-DEMO1234.pf")
        )
        assert evidence is not None
        path = _staging_path(settings, evidence)

    result = await PrefetchParserTool().execute(
        PrefetchParserParameters(file_path=str(path)),
        ToolExecutionContext(case_id=uuid.uuid4()),
    )

    assert result.status == "success"
    assert result.raw_output["total_executions"] >= 1
    assert result.raw_output["executions"][0]["executable_name"] == "POWERSHELL.EXE"


def test_seed_repairs_corrupted_readonly_staging_file(
    patched_seed: None,
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    seed_data.seed_demo_data()

    with session_factory() as session:
        evidence = session.scalar(select(Evidence).where(Evidence.original_name == "Security.evtx"))
        assert evidence is not None
        expected_sha256 = evidence.sha256
        path = _staging_path(settings, evidence)

    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    path.write_bytes(b"corrupted-demo-bytes")
    os.chmod(path, seed_data.SEALED_FILE_MODE)

    seed_data.seed_demo_data()

    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256
    assert stat.S_IMODE(path.stat().st_mode) & 0o222 == 0


def test_seed_repairs_deactivated_user_altered_role_and_closed_case(
    patched_seed: None,
    session_factory: sessionmaker[Session],
) -> None:
    seed_data.seed_demo_data()

    with session_factory() as session:
        analyst = session.scalar(select(User).where(User.email == "analyst@iryx.local"))
        assert analyst is not None
        analyst.is_active = False
        membership = session.scalar(select(Membership).where(Membership.user_id == analyst.id))
        assert membership is not None
        membership.role = MembershipRole.VIEWER.value
        case = session.scalar(select(Case).where(Case.title == seed_data.CASE_TITLE))
        assert case is not None
        case.status = CaseStatus.CLOSED
        case.description = ""
        case.created_by = None
        session.commit()

    seed_data.seed_demo_data()

    with session_factory() as session:
        admin = session.scalar(select(User).where(User.email == seed_data.ADMIN_EMAIL))
        analyst = session.scalar(select(User).where(User.email == "analyst@iryx.local"))
        assert admin is not None
        assert analyst is not None
        assert analyst.is_active is True
        membership = session.scalar(select(Membership).where(Membership.user_id == analyst.id))
        assert membership is not None
        assert membership.role == MembershipRole.ANALYST.value
        case = session.scalar(select(Case).where(Case.title == seed_data.CASE_TITLE))
        assert case is not None
        assert case.status == CaseStatus.OPEN
        assert case.description == seed_data.CASE_DESCRIPTION
        assert case.created_by == admin.id


def test_cli_module_runs_in_clean_subprocess_without_import_cycle(temp_dir: Path) -> None:
    db_path = temp_dir / "seed_cli.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(bind=engine)
    engine.dispose()

    env = os.environ.copy()
    env["SECRET_KEY"] = "unit-test-secret-key-min-32-chars-long"
    env["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    env["EVIDENCE_STORAGE_PATH"] = str(temp_dir)
    env["EVIDENCE_STAGING_PATH"] = str(temp_dir / "staging")
    env["PYTHONIOENCODING"] = "utf-8"

    backend_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, "-m", "iryx.scripts.seed_data"],
        cwd=str(backend_root),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "ImportError" not in completed.stderr
    assert seed_data.ORGANIZATION_NAME in completed.stdout


def test_main_prints_credentials_and_password_warning(
    patched_seed: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert seed_data.main() == 0

    output = capsys.readouterr().out
    assert seed_data.ORGANIZATION_NAME in output
    assert seed_data.CASE_TITLE in output
    for spec in seed_data.DEMO_USERS:
        assert spec.email in output
        assert spec.password in output
    assert "AVERTISSEMENT" in output
    assert "mots de passe robustes" in output
    assert "monstration" in output.lower()
    assert "Idempotence" in output


def test_main_returns_nonzero_when_staging_directory_is_unavailable(
    patched_seed: None,
    temp_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    blocker = temp_dir / "blocker"
    blocker.write_text("this is a file, not a directory", encoding="utf-8")
    bad_settings = Settings(
        secret_key="unit-test-secret-key-min-32-chars-long",
        evidence_storage_path=str(temp_dir),
        evidence_staging_path=str(blocker / "staging"),
    )

    with patch("iryx.scripts.seed_data.get_settings", return_value=bad_settings):
        assert seed_data.main() == 1

    captured = capsys.readouterr()
    assert "[ERREUR]" in captured.err
    assert "staging" in captured.err


def test_main_returns_nonzero_on_database_error(
    patched_seed: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_error = OperationalError(
        "SELECT 1",
        {},
        Exception("database unavailable"),
    )

    with patch("iryx.scripts.seed_data.SessionLocal", side_effect=database_error):
        assert seed_data.main() == 1

    captured = capsys.readouterr()
    assert "[ERREUR]" in captured.err
    assert "database unavailable" in captured.err


def test_main_returns_nonzero_when_staging_file_cannot_be_written(
    patched_seed: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(Path, "write_bytes", side_effect=OSError("disk full")):
        assert seed_data.main() == 1

    captured = capsys.readouterr()
    assert "[ERREUR]" in captured.err
    assert "disk full" in captured.err


def test_main_returns_nonzero_when_staging_path_is_blank(
    patched_seed: None,
    temp_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad_settings = Settings(
        secret_key="unit-test-secret-key-min-32-chars-long",
        evidence_storage_path=str(temp_dir),
        evidence_staging_path="   ",
    )

    with patch("iryx.scripts.seed_data.get_settings", return_value=bad_settings):
        assert seed_data.main() == 1

    captured = capsys.readouterr()
    assert "[ERREUR]" in captured.err
    assert "vide" in captured.err
