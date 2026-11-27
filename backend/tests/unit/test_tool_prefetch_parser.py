"""Unit tests for PrefetchParserTool: prefetch parsing and ToolRunner integration."""

import hashlib
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from dissect.target.plugins.os.windows.prefetch import c_prefetch
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.analytics.models import Observation
from iryx.auth.models import Organization
from iryx.cases.models import Case
from iryx.core.config import get_settings
from iryx.core.exceptions import ToolExecutionFailedException, ValidationException
from iryx.db.base import Base
from iryx.evidence.models import Evidence
from iryx.gateway.base import ToolExecutionContext
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.gateway.registry import default_registry
from iryx.gateway.runner import ToolRunner
from iryx.gateway.tools.prefetch_parser import (
    PrefetchParserParameters,
    PrefetchParserTool,
    PrefetchParsingError,
    sanitize_loaded_files,
    sanitize_path,
)


@pytest.fixture(autouse=True)
def _confine_evidence_to_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure evidence storage and staging paths to tmp_path for unit tests."""
    settings = get_settings()
    monkeypatch.setattr(settings, "evidence_storage_path", str(tmp_path))
    monkeypatch.setattr(settings, "evidence_staging_path", str(tmp_path / "staging"))


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide an in-memory SQLite session with foreign key enforcement."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_case(db_session: Session) -> Case:
    """Provide a persisted test Case entity."""
    org = Organization(name="CERT Prefetch Test")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Analyse Prefetch Windows")
    db_session.add(case)
    db_session.commit()
    return case


@pytest.fixture
def test_evidence(db_session: Session, test_case: Case) -> Evidence:
    """Provide a persisted test Evidence entity."""
    evidence = Evidence(
        case_id=test_case.id,
        original_name="NOTEPAD.EXE-1234ABCD.pf",
        file_size=65536,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    db_session.add(evidence)
    db_session.commit()
    return evidence


def create_synthetic_prefetch_scca(
    version: int = 30,
    executable_name: str = "NOTEPAD.EXE",
    prefetch_hash: int = 0x1234ABCD,
    run_count: int = 3,
    last_run_time: int = 132470784000000000,
    previous_runs: list[int] | None = None,
    dlls: list[str] | None = None,
    volumes: list[tuple[str, int, int]] | None = None,
) -> bytes:
    """Build a synthetic uncompressed binary SCCA Prefetch stream for testing."""
    dlls = dlls if dlls is not None else [r"\DEVICE\HARDDISKVOLUME3\WINDOWS\SYSTEM32\NTDLL.DLL"]
    volumes = (
        volumes
        if volumes is not None
        else [(r"\DEVICE\HARDDISKVOLUME3", 0xA1B2C3D4, 132470700000000000)]
    )

    header = c_prefetch.PREFETCH_HEADER()
    header.version = version
    header.signature = b"SCCA"
    header.name = executable_name.encode("utf-16-le").ljust(60, b"\x00")
    header.hash = prefetch_hash

    if version in (30, 31):
        fn = c_prefetch.FILE_INFORMATION_26()
        fn_size = 224
        metric_struct = c_prefetch.FILE_METRICS_ARRAY_ENTRY_23
        metric_size = 32
        vol_struct = c_prefetch.VOLUME_INFORMATION_30
        vol_size = 96
        prev = (
            previous_runs if previous_runs is not None else [132470783000000000, 132470782000000000]
        )
        fn.last_run_remains = (prev + [0] * 7)[:7]
    elif version == 23:
        fn = c_prefetch.FILE_INFORMATION_23()
        fn_size = 160
        metric_struct = c_prefetch.FILE_METRICS_ARRAY_ENTRY_23
        metric_size = 32
        vol_struct = c_prefetch.VOLUME_INFORMATION_17
        vol_size = 40
        prev = previous_runs if previous_runs is not None else [132470783000000000]
        fn.last_run_remains = (prev + [0] * 2)[:2]
    else:
        fn = c_prefetch.FILE_INFORMATION_17()
        fn_size = 52
        metric_struct = c_prefetch.FILE_METRICS_ARRAY_ENTRY_17
        metric_size = 20
        vol_struct = c_prefetch.VOLUME_INFORMATION_17
        vol_size = 40

    fn.last_run_time = last_run_time
    fn.run_count = run_count

    metrics_offset = 84 + fn_size
    fn.metrics_array_offset = metrics_offset
    fn.number_of_file_metrics_entries = len(dlls)

    strings_offset = metrics_offset + (len(dlls) * metric_size)
    fn.filename_strings_offset = strings_offset

    dll_data = bytearray()
    metric_records = []
    for dll in dlls:
        m = metric_struct()
        m.filename_string_offset = len(dll_data)
        m.filename_string_number_of_characters = len(dll)
        metric_records.append(m)
        dll_data.extend(dll.encode("utf-16-le"))

    fn.filename_strings_size = len(dll_data)

    vol_offset = strings_offset + len(dll_data)
    fn.volumes_information_offset = vol_offset
    fn.number_of_volumes = len(volumes)

    vol_data = bytearray()
    for dev_path, serial, ctime in volumes:
        v = vol_struct()
        v.creation_time = ctime
        v.serial_number = serial
        v.device_path_number_of_characters = len(dev_path)
        v.device_path_offset = vol_size
        path_bytes = dev_path.encode("utf-16-le")
        vol_data.extend(v.dumps())
        vol_data.extend(path_bytes)

    fn.volumes_information_size = len(vol_data)

    total_size = vol_offset + len(vol_data)
    header.size = total_size

    buf = bytearray(total_size)
    buf[0:84] = header.dumps()
    buf[84 : 84 + fn_size] = fn.dumps()
    cur = metrics_offset
    for m in metric_records:
        buf[cur : cur + metric_size] = m.dumps()
        cur += metric_size
    buf[strings_offset : strings_offset + len(dll_data)] = dll_data
    buf[vol_offset : vol_offset + len(vol_data)] = vol_data

    return bytes(buf)


def create_synthetic_mam_prefetch(scca_bytes: bytes) -> bytes:
    """Wrap SCCA prefetch bytes in a MAM compressed header."""
    header = bytearray(8)
    header[0:4] = b"MAM\x04"
    header[4:8] = len(scca_bytes).to_bytes(4, "little")
    return bytes(header) + b"\x00" * 32


# ---------------------------------------------------------------------------
# Unit tests: Path and Dependency Sanitization
# ---------------------------------------------------------------------------


def test_sanitize_path_nominal_and_null_bytes() -> None:
    """Test path sanitization removes null bytes and normalizes slashes."""
    p1 = r"\Device\HarddiskVolume3\Windows\System32\ntdll.dll"
    assert sanitize_path(p1) == p1

    p2 = r"C:\Windows\System32\calc.exe" + "\x00\x00"
    assert sanitize_path(p2) == r"C:\Windows\System32\calc.exe"

    p3 = "C:/Windows/System32/kernel32.dll"
    assert sanitize_path(p3) == r"C:\Windows\System32\kernel32.dll"


def test_sanitize_path_anti_traversal() -> None:
    """Test path sanitization prevents directory traversal attacks."""
    p1 = r"\Device\HarddiskVolume3\Windows\..\System32\ntdll.dll"
    assert sanitize_path(p1) == r"\Device\HarddiskVolume3\System32\ntdll.dll"

    p2 = r"..\..\..\malicious.dll"
    assert sanitize_path(p2) == "malicious.dll"

    p3 = r"\Device\HarddiskVolume3\..\..\..\WINDOWS"
    assert sanitize_path(p3) == r"\WINDOWS"

    p4 = r"\\server\share\..\folder\file.exe"
    assert sanitize_path(p4) == r"\\server\folder\file.exe"


def test_sanitize_loaded_files_truncation() -> None:
    """Test loaded file dependencies list truncation when exceeding 1000 items."""
    normal_files = [f"\\Device\\HarddiskVolume3\\file_{i}.dll" for i in range(50)]
    files, count, truncated = sanitize_loaded_files(normal_files)
    assert count == 50
    assert len(files) == 50
    assert truncated is False

    huge_files = [f"\\Device\\HarddiskVolume3\\file_{i}.dll\x00" for i in range(1500)]
    files, count, truncated = sanitize_loaded_files(huge_files)
    assert count == 1500
    assert len(files) == 1000
    assert truncated is True
    assert files[0] == r"\Device\HarddiskVolume3\file_0.dll"


# ---------------------------------------------------------------------------
# Unit tests: Parameters Schema Validation
# ---------------------------------------------------------------------------


def test_parameters_validation() -> None:
    """Test Pydantic v2 validation for PrefetchParserParameters."""
    params = PrefetchParserParameters(file_path="C:/Windows/Prefetch/CMD.EXE-1234ABCD.pf")
    assert params.artifact_type == "prefetch"
    assert params.max_results == 5000

    with pytest.raises(ValidationError, match="Au moins une source de données doit être fournie"):
        PrefetchParserParameters()

    with pytest.raises(ValidationError):
        PrefetchParserParameters(file_path="foo.pf", artifact_type="evtx")  # type: ignore

    with pytest.raises(ValidationError):
        PrefetchParserParameters(file_path="foo.pf", unexpected_field="bar")  # type: ignore

    with pytest.raises(ValidationError):
        PrefetchParserParameters(file_path="foo.pf", max_results=0)
    with pytest.raises(ValidationError):
        PrefetchParserParameters(file_path="foo.pf", max_results=60000)


# ---------------------------------------------------------------------------
# Unit tests: Header and Magic Validation
# ---------------------------------------------------------------------------


def test_header_validation_file_too_small(tmp_path: Path) -> None:
    """Test rejection of files under 8 bytes."""
    tool = PrefetchParserTool()

    empty_file = tmp_path / "empty.pf"
    empty_file.write_bytes(b"")

    with pytest.raises(PrefetchParsingError, match="trop court ou vide"):
        tool._validate_and_read_prefetch(empty_file)

    four_bytes = tmp_path / "four.pf"
    four_bytes.write_bytes(b"MAM\x04")

    with pytest.raises(PrefetchParsingError, match="trop court ou vide"):
        tool._validate_and_read_prefetch(four_bytes)


def test_header_validation_invalid_magic(tmp_path: Path) -> None:
    """Test rejection of non-prefetch files with invalid magic."""
    tool = PrefetchParserTool()

    corrupt_file = tmp_path / "corrupt.pf"
    corrupt_file.write_bytes(b"NOT_PREFETCH_HEADER_DATA_1234567890")

    with pytest.raises(PrefetchParsingError, match="Format Prefetch non reconnu"):
        tool._validate_and_read_prefetch(corrupt_file)


def test_header_validation_mam_decompression_failure(tmp_path: Path) -> None:
    """Test error handling when MAM decompression fails."""
    tool = PrefetchParserTool()

    mam_file = tmp_path / "broken_mam.pf"
    mam_file.write_bytes(b"MAM\x04\x00\x10\x00\x00" + b"\xff" * 50)

    with (
        patch(
            "dissect.util.lzxpress_huffman.decompress",
            side_effect=Exception("Corrupt LZXpress data"),
        ),
        pytest.raises(PrefetchParsingError, match="Échec de décompression MAM"),
    ):
        tool._validate_and_read_prefetch(mam_file)


# ---------------------------------------------------------------------------
# Unit tests: Nominal Parsing (Win10 MAM and Win7 SCCA)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nominal_win10_mam_prefetch(tmp_path: Path) -> None:
    """Test nominal parsing of a Windows 10 MAM-compressed Prefetch file with 3 executions."""
    scca_bytes = create_synthetic_prefetch_scca(
        version=30,
        executable_name="NOTEPAD.EXE",
        prefetch_hash=0x1234ABCD,
        run_count=3,
        last_run_time=132470784000000000,
        previous_runs=[132470783000000000, 132470782000000000],
        dlls=[r"\Device\HarddiskVolume3\Windows\System32\ntdll.dll"],
        volumes=[(r"\Device\HarddiskVolume3", 0xA1B2C3D4, 132470700000000000)],
    )
    mam_bytes = create_synthetic_mam_prefetch(scca_bytes)
    pf_file = tmp_path / "NOTEPAD.EXE-1234ABCD.pf"
    pf_file.write_bytes(mam_bytes)

    tool = PrefetchParserTool()
    params = PrefetchParserParameters(file_path=str(pf_file))
    context = ToolExecutionContext(case_id=uuid.uuid4(), agent_role="Executor")

    with patch("dissect.util.lzxpress_huffman.decompress", return_value=scca_bytes):
        result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.raw_output["artifact_type"] == "prefetch"
    assert result.raw_output["files_analyzed"] == 1
    assert result.raw_output["total_executions"] == 3
    assert len(result.raw_output["executions"]) == 3
    assert len(result.observations) == 3

    obs0 = result.observations[0]
    assert obs0["timestamp_utc"] == datetime(2020, 10, 13, 16, 0, tzinfo=UTC)
    assert obs0["normalized_content"]["tool_name"] == "dissect.prefetch"
    assert obs0["normalized_content"]["executable_name"] == "NOTEPAD.EXE"
    assert obs0["normalized_content"]["prefetch_hash"] == "1234ABCD"
    assert obs0["normalized_content"]["run_count"] == 3
    assert obs0["normalized_content"]["execution_index"] == 0
    assert len(obs0["normalized_content"]["all_execution_timestamps_utc"]) == 3
    assert obs0["normalized_content"]["loaded_files_truncated"] is False
    expected_dll = r"\Device\HarddiskVolume3\Windows\System32\ntdll.dll"
    assert obs0["normalized_content"]["loaded_files"] == [expected_dll]
    assert obs0["normalized_content"]["loaded_files_count"] == 1
    assert len(obs0["normalized_content"]["volumes"]) == 1
    assert obs0["normalized_content"]["volumes"][0]["device_path"] == r"\Device\HarddiskVolume3"
    assert obs0["normalized_content"]["volumes"][0]["serial_number"] == "A1B2C3D4"
    assert obs0["normalized_content"]["volumes"][0]["creation_time_utc"] is not None

    assert result.observations[1]["normalized_content"]["execution_index"] == 1
    assert result.observations[2]["normalized_content"]["execution_index"] == 2


@pytest.mark.asyncio
async def test_nominal_win7_uncompressed_scca_prefetch(tmp_path: Path) -> None:
    """Test nominal parsing of a Windows 7 uncompressed SCCA Prefetch file."""
    scca_bytes = create_synthetic_prefetch_scca(
        version=23,
        executable_name="CALC.EXE",
        prefetch_hash=0x87654321,
        run_count=2,
        last_run_time=132470784000000000,
        previous_runs=[132470783000000000],
        dlls=[r"\Device\HarddiskVolume1\Windows\System32\calc.exe"],
        volumes=[(r"\Device\HarddiskVolume1", 0x11223344, 132470600000000000)],
    )
    pf_file = tmp_path / "CALC.EXE-87654321.pf"
    pf_file.write_bytes(scca_bytes)

    tool = PrefetchParserTool()
    params = PrefetchParserParameters(file_path=str(pf_file))
    context = ToolExecutionContext(case_id=uuid.uuid4(), agent_role="Executor")

    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.raw_output["files_analyzed"] == 1
    assert result.raw_output["total_executions"] == 2
    assert len(result.observations) == 2
    assert result.observations[0]["normalized_content"]["executable_name"] == "CALC.EXE"
    assert result.observations[0]["normalized_content"]["prefetch_hash"] == "87654321"


# ---------------------------------------------------------------------------
# Unit tests: Filters (executable_name, search_query, max_results)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executable_name_filter(tmp_path: Path) -> None:
    """Test filtering by executable name (case-insensitive and mismatch behavior)."""
    scca_bytes = create_synthetic_prefetch_scca(
        version=30,
        executable_name="NOTEPAD.EXE",
        run_count=1,
        previous_runs=[],
    )
    pf_file = tmp_path / "NOTEPAD.EXE-1234ABCD.pf"
    pf_file.write_bytes(scca_bytes)

    tool = PrefetchParserTool()
    context = ToolExecutionContext(case_id=uuid.uuid4(), agent_role="Executor")

    # Mismatch filter: executable_name="calc.exe"
    params_mismatch = PrefetchParserParameters(
        file_path=str(pf_file),
        executable_name="calc.exe",
    )
    res_mismatch = await tool.execute(params_mismatch, context)
    assert res_mismatch.raw_output["files_analyzed"] == 1
    assert res_mismatch.raw_output["total_executions"] == 0
    assert len(res_mismatch.observations) == 0

    # Matching filter: executable_name="notepad"
    params_match = PrefetchParserParameters(
        file_path=str(pf_file),
        executable_name="notepad",
    )
    res_match = await tool.execute(params_match, context)
    assert res_match.raw_output["files_analyzed"] == 1
    assert res_match.raw_output["total_executions"] == 1
    assert len(res_match.observations) == 1


@pytest.mark.asyncio
async def test_search_query_filter(tmp_path: Path) -> None:
    """Test text search query across dependencies, volume paths, and prefetch hash."""
    scca_bytes = create_synthetic_prefetch_scca(
        version=30,
        executable_name="CMD.EXE",
        prefetch_hash=0xDEADBEEF,
        dlls=[r"\Device\HarddiskVolume3\Windows\System32\shell32.dll"],
        volumes=[(r"\Device\HarddiskVolume3", 0x12345678, 132470700000000000)],
    )
    pf_file = tmp_path / "CMD.EXE-DEADBEEF.pf"
    pf_file.write_bytes(scca_bytes)

    tool = PrefetchParserTool()
    context = ToolExecutionContext(case_id=uuid.uuid4(), agent_role="Executor")

    # Match in dll name
    res1 = await tool.execute(
        PrefetchParserParameters(file_path=str(pf_file), search_query="shell32"),
        context,
    )
    assert len(res1.observations) == 3

    # Match in hash
    res2 = await tool.execute(
        PrefetchParserParameters(file_path=str(pf_file), search_query="deadbeef"),
        context,
    )
    assert len(res2.observations) == 3

    # Mismatch
    res3 = await tool.execute(
        PrefetchParserParameters(file_path=str(pf_file), search_query="nonexistent_string"),
        context,
    )
    assert len(res3.observations) == 0


@pytest.mark.asyncio
async def test_max_results_truncation(tmp_path: Path) -> None:
    """Test that max_results limits the number of generated observations."""
    scca_bytes = create_synthetic_prefetch_scca(
        version=30,
        run_count=3,
        previous_runs=[132470783000000000, 132470782000000000],
    )
    pf_file = tmp_path / "TEST.pf"
    pf_file.write_bytes(scca_bytes)

    tool = PrefetchParserTool()
    context = ToolExecutionContext(case_id=uuid.uuid4(), agent_role="Executor")

    params = PrefetchParserParameters(file_path=str(pf_file), max_results=2)
    res = await tool.execute(params, context)

    assert len(res.observations) == 2
    assert res.metadata["truncated"] is True


# ---------------------------------------------------------------------------
# Unit tests: Directory Parsing and Isolated Error Handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_directory_parsing_with_isolated_error(tmp_path: Path) -> None:
    """Test directory parsing handles multiple .pf files and logs corrupt files without failing."""
    dir_path = tmp_path / "PrefetchDir"
    dir_path.mkdir()

    # 1. Valid file 1
    scca1 = create_synthetic_prefetch_scca(executable_name="CMD.EXE", run_count=1)
    (dir_path / "CMD.EXE-11111111.pf").write_bytes(scca1)

    # 2. Valid file 2
    scca2 = create_synthetic_prefetch_scca(executable_name="NOTEPAD.EXE", run_count=1)
    (dir_path / "NOTEPAD.EXE-22222222.pf").write_bytes(scca2)

    # 3. Corrupt file
    (dir_path / "CORRUPT.pf").write_bytes(b"NOT_A_VALID_PREFETCH_HEADER")

    # 4. Non-pf file (should be ignored)
    (dir_path / "readme.txt").write_text("Ignore me")

    tool = PrefetchParserTool()
    params = PrefetchParserParameters(file_path=str(dir_path))
    context = ToolExecutionContext(case_id=uuid.uuid4(), agent_role="Executor")

    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.raw_output["files_analyzed"] == 3
    assert result.raw_output["total_executions"] == 6
    assert len(result.observations) == 6
    assert len(result.metadata["errors"]) == 1
    assert result.metadata["errors"][0]["file"] == "CORRUPT.pf"


# ---------------------------------------------------------------------------
# Unit tests: ToolRunner Integration and Persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_runner_success(
    db_session: Session,
    test_case: Case,
    test_evidence: Evidence,
    tmp_path: Path,
) -> None:
    """Test full ToolRunner execution persists ToolExecution and Observation entities."""
    scca_bytes = create_synthetic_prefetch_scca(
        version=30,
        executable_name="NOTEPAD.EXE",
        prefetch_hash=0x1234ABCD,
        run_count=3,
        last_run_time=132470784000000000,
        previous_runs=[132470783000000000, 132470782000000000],
    )
    pf_file = tmp_path / "NOTEPAD.EXE-1234ABCD.pf"
    pf_file.write_bytes(scca_bytes)

    runner = ToolRunner(db=db_session, registry=default_registry)
    context = ToolExecutionContext(
        case_id=test_case.id,
        evidence_id=test_evidence.id,
        agent_role="Executor",
    )

    result = await runner.execute_tool(
        tool_name="parse_execution",
        parameters={"file_path": str(pf_file), "artifact_type": "prefetch"},
        context=context,
    )

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.result_sha256 is not None
    assert len(result.result_sha256) == 64

    # Verify ToolExecution record in SQLite
    executions = db_session.query(ToolExecution).filter_by(case_id=test_case.id).all()
    assert len(executions) == 1
    te = executions[0]
    assert te.tool_name == "parse_execution"
    assert te.status == ToolExecutionStatus.SUCCESS
    assert te.result_sha256 == result.result_sha256
    assert te.duration_ms > 0

    # Verify Observation records in SQLite
    observations = db_session.query(Observation).filter_by(tool_execution_id=te.id).all()
    assert len(observations) == 3
    for obs in observations:
        assert obs.tool_name == "parse_execution"
        assert obs.case_id == test_case.id
        assert obs.source_id == test_evidence.id
        assert obs.timestamp_utc is not None
        obs_ts = obs.timestamp_utc
        if obs_ts.tzinfo is None:
            obs_ts = obs_ts.replace(tzinfo=UTC)
        assert obs_ts.year == 2020
        assert obs.normalized_content["executable_name"] == "NOTEPAD.EXE"


@pytest.mark.asyncio
async def test_tool_runner_error_on_corrupt_file(
    db_session: Session,
    test_case: Case,
    tmp_path: Path,
) -> None:
    """Test ToolRunner records status='error' when prefetch file header is corrupt."""
    bad_file = tmp_path / "broken.pf"
    bad_file.write_bytes(b"INVALID_PREFETCH_BYTES")

    runner = ToolRunner(db=db_session, registry=default_registry)
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")

    with pytest.raises(ToolExecutionFailedException, match="Erreur interne lors de l'exécution"):
        await runner.execute_tool(
            tool_name="parse_execution",
            parameters={"file_path": str(bad_file), "artifact_type": "prefetch"},
            context=context,
        )

    # Verify ToolExecution status is ERROR
    executions = db_session.query(ToolExecution).filter_by(case_id=test_case.id).all()
    assert len(executions) == 1
    te = executions[0]
    assert te.status == ToolExecutionStatus.ERROR
    assert te.error_message is not None
    assert te.result_sha256 is None

    # No observations persisted
    obs_count = db_session.query(Observation).count()
    assert obs_count == 0


@pytest.mark.asyncio
async def test_tool_runner_source_not_found(
    tmp_path: Path,
    db_session: Session,
    test_case: Case,
) -> None:
    """Test ValidationException on missing source and verify zero persistence."""
    runner = ToolRunner(db=db_session, registry=default_registry)
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")

    with pytest.raises(ValidationException, match="introuvable"):
        await runner.execute_tool(
            tool_name="parse_execution",
            parameters={"file_path": str(tmp_path / "NonExistent" / "Prefetch.pf")},
            context=context,
        )

    assert db_session.query(ToolExecution).count() == 0
    assert db_session.query(Observation).count() == 0


@pytest.mark.asyncio
async def test_tool_runner_success_via_evidence_id_in_staging(
    db_session: Session,
    test_case: Case,
    test_evidence: Evidence,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test resolving evidence by evidence_id alone from staging path."""
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)

    from iryx.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "evidence_staging_path", str(staging_dir))
    monkeypatch.setattr(settings, "evidence_storage_path", str(storage_dir))

    scca_bytes = create_synthetic_prefetch_scca(version=30, executable_name="CMD.EXE")
    staged_file = staging_dir / f"{test_evidence.id}.pf"
    staged_file.write_bytes(scca_bytes)

    runner = ToolRunner(db=db_session, registry=default_registry)
    context = ToolExecutionContext(
        case_id=test_case.id,
        evidence_id=test_evidence.id,
        agent_role="Executor",
    )

    result = await runner.execute_tool(
        tool_name="parse_execution",
        parameters={"evidence_id": str(test_evidence.id), "artifact_type": "prefetch"},
        context=context,
    )

    assert result.status == ToolExecutionStatus.SUCCESS
    obs = db_session.query(Observation).filter_by(case_id=test_case.id).first()
    assert obs is not None
    assert obs.source_id == test_evidence.id
    assert obs.normalized_content["executable_name"] == "CMD.EXE"


@pytest.mark.asyncio
async def test_tool_runner_evidence_id_not_found(
    db_session: Session,
    test_case: Case,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test ValidationException when evidence_id does not exist in staging or storage."""
    from iryx.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "evidence_staging_path", str(tmp_path / "empty_staging"))
    monkeypatch.setattr(settings, "evidence_storage_path", str(tmp_path / "empty_storage"))

    runner = ToolRunner(db=db_session, registry=default_registry)
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")
    missing_id = uuid.uuid4()

    with pytest.raises(ValidationException, match="Preuve introuvable pour l'identifiant"):
        await runner.execute_tool(
            tool_name="parse_execution",
            parameters={"evidence_id": str(missing_id), "artifact_type": "prefetch"},
            context=context,
        )

    assert db_session.query(ToolExecution).count() == 0
    assert db_session.query(Observation).count() == 0


@pytest.mark.asyncio
async def test_search_query_matches_volume_serial(tmp_path: Path) -> None:
    """Test searching by volume serial number."""
    scca_bytes = create_synthetic_prefetch_scca(
        version=30,
        executable_name="POWERSHELL.EXE",
        volumes=[(r"\Device\HarddiskVolume1", 0xBEEFCAFE, 132470700000000000)],
    )
    pf_file = tmp_path / "POWERSHELL.EXE-11223344.pf"
    pf_file.write_bytes(scca_bytes)

    tool = PrefetchParserTool()
    params = PrefetchParserParameters(file_path=str(pf_file), search_query="beefcafe")
    context = ToolExecutionContext(case_id=uuid.uuid4(), agent_role="Executor")

    result = await tool.execute(params, context)
    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 3
    assert result.observations[0]["normalized_content"]["executable_name"] == "POWERSHELL.EXE"


# ---------------------------------------------------------------------------
# Unit tests: Passive Forensic Integrity (Read-Only)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_passive_forensic_read_only_integrity(tmp_path: Path) -> None:
    """Verify that analyzing a Prefetch file does not alter its SHA-256 hash or contents."""
    scca_bytes = create_synthetic_prefetch_scca(version=30, executable_name="CMD.EXE")
    pf_file = tmp_path / "CMD.EXE-12345678.pf"
    pf_file.write_bytes(scca_bytes)

    initial_sha = hashlib.sha256(pf_file.read_bytes()).hexdigest()

    tool = PrefetchParserTool()
    params = PrefetchParserParameters(file_path=str(pf_file))
    context = ToolExecutionContext(case_id=uuid.uuid4(), agent_role="Executor")

    result = await tool.execute(params, context)
    assert result.status == ToolExecutionStatus.SUCCESS

    final_sha = hashlib.sha256(pf_file.read_bytes()).hexdigest()
    assert initial_sha == final_sha


def test_default_registry_contains_prefetch_parser() -> None:
    """Verify default_registry includes PrefetchParserTool automatically."""
    assert default_registry.has("parse_execution")
    tool = default_registry.get("parse_execution")
    assert isinstance(tool, PrefetchParserTool)
    assert tool.name == "parse_execution"
    assert tool.timeout_seconds == 120
