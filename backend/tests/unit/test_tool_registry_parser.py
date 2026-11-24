"""Unit tests for RegistryParserTool: registry parsing, UTC normalization, and ToolRunner."""

import codecs
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from regipy.exceptions import RegistryKeyNotFoundException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.analytics.models import Observation
from iryx.auth.models import Organization
from iryx.cases.models import Case
from iryx.core.exceptions import ToolExecutionFailedException, ValidationException
from iryx.db.base import Base
from iryx.evidence.models import Evidence
from iryx.gateway.base import ToolExecutionContext
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.gateway.registry import default_registry
from iryx.gateway.runner import ToolRunner
from iryx.gateway.tools.registry_parser import (
    REGISTRY_MAGIC,
    RegistryHiveParsingError,
    RegistryParserParameters,
    RegistryParserTool,
    filetime_to_utc,
    is_user_assist_count,
    normalize_key_path,
    normalize_value_data,
)


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
    org = Organization(name="CERT Registry Test")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Analyse Registre Windows")
    db_session.add(case)
    db_session.commit()
    return case


@pytest.fixture
def test_evidence(db_session: Session, test_case: Case) -> Evidence:
    """Provide a persisted test Evidence entity."""
    evidence = Evidence(
        case_id=test_case.id,
        original_name="SYSTEM",
        file_size=65536,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    db_session.add(evidence)
    db_session.commit()
    return evidence


def make_mock_value(
    name: str,
    value: Any,
    value_type: str = "REG_SZ",
    is_corrupted: bool = False,
) -> MagicMock:
    """Create a mock Value entry for an NKRecord."""
    val = MagicMock()
    val.name = name
    val.value = value
    val.value_type = value_type
    val.is_corrupted = is_corrupted
    return val


def make_mock_key(
    name: str = "Key",
    values: list[Any] | None = None,
    subkeys: list[Any] | None = None,
    last_modified: int = 132470000000000000,  # 2020-10-12T18:13:20Z
) -> MagicMock:
    """Create a mock NKRecord key."""
    key = MagicMock()
    key.name = name
    key.header.last_modified = last_modified
    if values is not None:
        key.values_count = len(values)
        key.iter_values.side_effect = lambda as_json=False, trim_values=False: iter(values)
    else:
        key.values_count = 0
        key.iter_values.return_value = None

    if subkeys is not None:
        key.subkey_count = len(subkeys)
        key.iter_subkeys.side_effect = lambda: iter(subkeys)
    else:
        key.subkey_count = 0
        key.iter_subkeys.return_value = None
    return key


def create_mock_hive(
    key_map: dict[str, Any],
    hive_type: str | None = None,
    file_name: str | None = None,
) -> MagicMock:
    """Create a mock RegistryHive object with case-insensitive path lookup."""
    mock_hive = MagicMock()
    mock_hive.hive_type = hive_type
    mock_hive.name = file_name

    def get_key_side_effect(path: str):
        norm = normalize_key_path(path).lower()
        for k, v in key_map.items():
            if normalize_key_path(k).lower() == norm:
                return v
        raise RegistryKeyNotFoundException(f"Did not find subkey at {path}")

    mock_hive.get_key.side_effect = get_key_side_effect
    return mock_hive


# --- Unit Tests: Helper Functions & Schema Validation ---


def test_filetime_to_utc() -> None:
    """Verify FILETIME conversion to timezone-aware UTC datetime."""
    # Standard FILETIME for 2020-10-12 18:13:20 UTC
    ft = 132470000000000000
    dt = filetime_to_utc(ft)
    assert dt is not None
    assert dt.tzinfo == UTC
    assert dt == datetime(2020, 10, 12, 18, 13, 20, tzinfo=UTC)

    # 0 or None -> None
    assert filetime_to_utc(0) is None
    assert filetime_to_utc(None) is None
    assert filetime_to_utc(0x7FFFFFFFFFFFFFFF) is None


def test_normalize_key_path() -> None:
    """Verify normalization of registry key paths."""
    assert normalize_key_path("Software/Microsoft/Windows") == r"\Software\Microsoft\Windows"
    assert normalize_key_path("/Software/Microsoft/Windows") == r"\Software\Microsoft\Windows"
    assert normalize_key_path(r"\Software\\Microsoft\Windows") == r"\Software\Microsoft\Windows"
    assert normalize_key_path(r"Software\Microsoft") == r"\Software\Microsoft"
    assert normalize_key_path("\\") == "\\"


def test_is_user_assist_count() -> None:
    """Verify detection of UserAssist Count keys."""
    guid_path = (
        r"\Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"
        r"\{75048700-EF1F-11D0-9888-006097DEACF9}\Count"
    )
    assert is_user_assist_count(guid_path) is True
    assert is_user_assist_count(r"\Software\Microsoft\Windows\CurrentVersion\Run") is False
    assert is_user_assist_count(r"\UserAssist\Count") is True


def test_normalize_value_data() -> None:
    """Verify value data serialization, null byte removal, and binary truncation."""
    # String with null bytes
    val_str, trunc_str = normalize_value_data("cmd.exe\x00 -arg")
    assert val_str == "cmd.exe -arg"
    assert trunc_str is False

    # List of strings (REG_MULTI_SZ)
    val_list, trunc_list = normalize_value_data(["line1\x00", "line2"])
    assert val_list == ["line1", "line2"]
    assert trunc_list is False

    # Numeric DWORD
    val_int, trunc_int = normalize_value_data(1234)
    assert val_int == 1234
    assert trunc_int is False

    # Binary data under 4096 bytes
    small_bytes = b"\x01\x02\x03\x04"
    val_b, trunc_b = normalize_value_data(small_bytes)
    assert val_b == "01020304"
    assert trunc_b is False

    # Binary data over 4096 bytes
    large_bytes = b"A" * 10000
    val_large, trunc_large = normalize_value_data(large_bytes)
    assert len(val_large) == 4096 * 2  # Hex encoding of 4096 bytes
    assert val_large == (b"A" * 4096).hex()
    assert trunc_large is True


def test_registry_parameters_validation() -> None:
    """Verify RegistryParserParameters validates sources and bounds."""
    # 1. Missing both evidence_id and file_path
    with pytest.raises(ValidationError) as exc:
        RegistryParserParameters()
    assert "Au moins une source de données doit être fournie" in str(exc.value)

    # 2. Valid with file_path and defaults
    p = RegistryParserParameters(file_path="SYSTEM")
    assert p.file_path == "SYSTEM"
    assert p.hive_type == "auto"
    assert p.recursive is True
    assert p.max_depth == 10
    assert p.max_values == 5000

    # 3. Extra fields forbidden
    with pytest.raises(ValidationError):
        RegistryParserParameters.model_validate(
            {"file_path": "SYSTEM", "unexpected_field": "forbidden"}
        )

    # 4. max_depth boundaries
    with pytest.raises(ValidationError):
        RegistryParserParameters(file_path="SYSTEM", max_depth=0)
    with pytest.raises(ValidationError):
        RegistryParserParameters(file_path="SYSTEM", max_depth=33)

    # 5. max_values boundaries
    with pytest.raises(ValidationError):
        RegistryParserParameters(file_path="SYSTEM", max_values=0)
    with pytest.raises(ValidationError):
        RegistryParserParameters(file_path="SYSTEM", max_values=50001)

    # 6. key_paths max 50
    too_many_paths = [f"\\Key_{i}" for i in range(51)]
    with pytest.raises(ValidationError):
        RegistryParserParameters(file_path="SYSTEM", key_paths=too_many_paths)


# --- Unit Tests: I/O & Edge-Case Matrix Scenarios ---


@pytest.mark.asyncio
async def test_scenario_run_ntuser_nominal(tmp_path: Path) -> None:
    """Matrix Row 1: Run NTUSER nominal - 2 values extracted, source_location, timestamp_utc."""
    hive_file = tmp_path / "NTUSER.DAT"
    hive_file.write_bytes(REGISTRY_MAGIC + b"\x00" * 4092)

    val1 = make_mock_value("SecurityApp", "C:\\Program Files\\Sec\\app.exe", "REG_SZ")
    val2 = make_mock_value("OneDrive", "C:\\Users\\User\\AppData\\OneDrive.exe", "REG_SZ")
    run_key = make_mock_key(
        name="Run",
        values=[val1, val2],
        last_modified=132470000000000000,
    )

    key_path = r"\Software\Microsoft\Windows\CurrentVersion\Run"
    mock_hive = create_mock_hive({key_path: run_key}, hive_type="ntuser")

    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = RegistryParserParameters(
        file_path=str(hive_file),
        hive_type="ntuser",
        key_paths=[key_path],
    )

    with patch("iryx.gateway.tools.registry_parser.RegistryHive", return_value=mock_hive):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2
    assert result.metadata["parsed_values_count"] == 2
    assert result.metadata["truncated"] is False

    obs1 = result.observations[0]
    assert obs1["source_location"] == key_path
    assert obs1["timestamp_utc"] == datetime(2020, 10, 12, 18, 13, 20, tzinfo=UTC)
    assert obs1["normalized_content"]["value_name"] == "SecurityApp"
    assert obs1["normalized_content"]["value_data"] == "C:\\Program Files\\Sec\\app.exe"
    assert obs1["normalized_content"]["hive_type"] == "ntuser"

    obs2 = result.observations[1]
    assert obs2["source_location"] == key_path
    assert obs2["timestamp_utc"] == datetime(2020, 10, 12, 18, 13, 20, tzinfo=UTC)
    assert obs2["normalized_content"]["value_name"] == "OneDrive"


@pytest.mark.asyncio
async def test_scenario_recursion_services_system(tmp_path: Path) -> None:
    """Matrix Row 2: Recursion Services - ControlSet00N resolved, recursive subkeys extracted."""
    hive_file = tmp_path / "SYSTEM"
    hive_file.write_bytes(REGISTRY_MAGIC + b"\x00" * 4092)

    # \Select key points to Current = 2 -> ControlSet002
    select_val = make_mock_value("Current", 2, "REG_DWORD")
    select_key = make_mock_key("Select", values=[select_val])

    # Under ControlSet002\Services\LanmanServer
    srv_val = make_mock_value("ImagePath", "system32\\srv2.sys", "REG_EXPAND_SZ")
    sub_key = make_mock_key("LanmanServer", values=[srv_val])
    services_key = make_mock_key("Services", values=[], subkeys=[sub_key])

    mock_hive = create_mock_hive(
        {
            r"\Select": select_key,
            r"\ControlSet002\Services": services_key,
        },
        hive_type="system",
    )

    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = RegistryParserParameters(
        file_path=str(hive_file),
        hive_type="system",
        key_paths=[r"\CurrentControlSet\Services"],
        recursive=True,
    )

    with patch("iryx.gateway.tools.registry_parser.RegistryHive", return_value=mock_hive):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    obs = result.observations[0]
    assert obs["source_location"] == r"\ControlSet002\Services\LanmanServer"
    assert obs["normalized_content"]["value_name"] == "ImagePath"
    assert obs["normalized_content"]["value_data"] == "system32\\srv2.sys"
    assert r"\ControlSet002\Services" in result.metadata["resolved_key_paths"]


@pytest.mark.asyncio
async def test_scenario_presets_software(tmp_path: Path) -> None:
    """Matrix Row 3: Presets for software - Run traversed, missing listed in missing_keys."""
    hive_file = tmp_path / "SOFTWARE"
    hive_file.write_bytes(REGISTRY_MAGIC + b"\x00" * 4092)

    run_val = make_mock_value("Defender", "C:\\Windows\\def.exe", "REG_SZ")
    run_key = make_mock_key("Run", values=[run_val])

    # Only Run exists, other default presets (RunOnce, Winlogon...) will be missing
    mock_hive = create_mock_hive(
        {
            r"\Microsoft\Windows\CurrentVersion\Run": run_key,
        },
        hive_type="software",
    )

    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    # No key_paths provided -> use presets for software
    params = RegistryParserParameters(file_path=str(hive_file), hive_type="software")

    with patch("iryx.gateway.tools.registry_parser.RegistryHive", return_value=mock_hive):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["normalized_content"]["value_name"] == "Defender"
    # Missing presets are listed in metadata.missing_keys without causing failure
    assert len(result.metadata["missing_keys"]) > 0
    assert r"\Microsoft\Windows\CurrentVersion\RunOnce" in result.metadata["missing_keys"]


@pytest.mark.asyncio
async def test_scenario_user_assist_rot13_decoding(tmp_path: Path) -> None:
    """Matrix Row 4: UserAssist - value 'HRZR_EHACNGU' under Count decoded to 'UEME_RUNPATH'."""
    hive_file = tmp_path / "NTUSER.DAT"
    hive_file.write_bytes(REGISTRY_MAGIC + b"\x00" * 4092)

    # ROT13 encoded name: "HRZR_EHACNGU" -> "UEME_RUNPATH"
    raw_val_name = "HRZR_EHACNGU"
    val = make_mock_value(raw_val_name, b"\x00" * 16, "REG_BINARY")

    count_path = (
        r"\Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"
        r"\{CEBFF5CD-ACE2-4F4F-9178-9926F41749EA}\Count"
    )
    count_key = make_mock_key("Count", values=[val])

    mock_hive = create_mock_hive({count_path: count_key}, hive_type="ntuser")

    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = RegistryParserParameters(
        file_path=str(hive_file),
        hive_type="ntuser",
        key_paths=[count_path],
    )

    with patch("iryx.gateway.tools.registry_parser.RegistryHive", return_value=mock_hive):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    content = result.observations[0]["normalized_content"]
    assert content["value_name"] == "HRZR_EHACNGU"
    assert "decoded_value_name" in content
    assert content["decoded_value_name"] == "UEME_RUNPATH"
    assert codecs.decode("HRZR_EHACNGU", "rot-13") == "UEME_RUNPATH"


@pytest.mark.asyncio
async def test_scenario_binary_data_truncation(tmp_path: Path) -> None:
    """Matrix Row 5: Binary data - 10 000 bytes truncated to hex of 4096 bytes and flagged."""
    hive_file = tmp_path / "SYSTEM"
    hive_file.write_bytes(REGISTRY_MAGIC + b"\x00" * 4092)

    raw_binary = b"\xaa" * 10000
    val = make_mock_value("BigData", raw_binary, "REG_BINARY")
    key = make_mock_key("TestKey", values=[val])

    key_path = r"\ControlSet001\Services\TestService"
    mock_hive = create_mock_hive({key_path: key}, hive_type="system")

    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = RegistryParserParameters(
        file_path=str(hive_file),
        hive_type="system",
        key_paths=[key_path],
    )

    with patch("iryx.gateway.tools.registry_parser.RegistryHive", return_value=mock_hive):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    content = result.observations[0]["normalized_content"]
    assert content["value_data_truncated"] is True
    assert content["value_data"] == (b"\xaa" * 4096).hex()
    assert len(content["value_data"]) == 4096 * 2


@pytest.mark.asyncio
async def test_scenario_max_values_ceiling_truncation(tmp_path: Path) -> None:
    """Matrix Row 6: Ceiling limit - 300 values extracted with max_values=100 -> truncated=True."""
    hive_file = tmp_path / "NTUSER.DAT"
    hive_file.write_bytes(REGISTRY_MAGIC + b"\x00" * 4092)

    values = [make_mock_value(f"Val_{i}", f"Data_{i}", "REG_SZ") for i in range(300)]
    key = make_mock_key("BigKey", values=values)

    key_path = r"\Software\TestApp"
    mock_hive = create_mock_hive({key_path: key}, hive_type="ntuser")

    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = RegistryParserParameters(
        file_path=str(hive_file),
        hive_type="ntuser",
        key_paths=[key_path],
        max_values=100,
    )

    with patch("iryx.gateway.tools.registry_parser.RegistryHive", return_value=mock_hive):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 100
    assert result.metadata["parsed_values_count"] == 100
    assert result.metadata["truncated"] is True
    assert result.raw_output["values_count"] == 100


@pytest.mark.asyncio
async def test_scenario_invalid_header_rejection(tmp_path: Path) -> None:
    """Matrix Row 7: Invalid header (< 4096 bytes or bad magic) raises RegistryHiveParsingError."""
    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())

    # Case A: File smaller than 4096 bytes
    small_file = tmp_path / "corrupt_small.hiv"
    small_file.write_bytes(b"regf" + b"\x00" * 100)
    params_small = RegistryParserParameters(file_path=str(small_file))

    with pytest.raises(RegistryHiveParsingError) as exc_small:
        await tool.execute(params_small, ctx)
    assert "Format de ruche de Registre non reconnu ou corrompu" in str(exc_small.value)

    # Case B: File >= 4096 bytes but wrong magic
    bad_magic_file = tmp_path / "corrupt_bad_magic.hiv"
    bad_magic_file.write_bytes(b"TEST" + b"\x00" * 4092)
    params_bad = RegistryParserParameters(file_path=str(bad_magic_file))

    with pytest.raises(RegistryHiveParsingError) as exc_bad:
        await tool.execute(params_bad, ctx)
    assert "Format de ruche de Registre non reconnu ou corrompu" in str(exc_bad.value)


@pytest.mark.asyncio
async def test_scenario_source_not_found(tmp_path: Path) -> None:
    """Matrix Row 8: Non-existent evidence_id or file_path raises ValidationException."""
    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())

    # Inexistent file_path
    params = RegistryParserParameters(file_path=str(tmp_path / "non_existent.hiv"))
    with pytest.raises(ValidationException) as exc:
        await tool.execute(params, ctx)
    assert "Fichier de Registre introuvable" in str(exc.value)

    # Inexistent evidence_id
    params_evidence = RegistryParserParameters(evidence_id=uuid.uuid4())
    with pytest.raises(ValidationException) as exc_ev:
        await tool.execute(params_evidence, ctx)
    assert "Fichier de preuve introuvable" in str(exc_ev.value)


@pytest.mark.asyncio
async def test_scenario_unidentifiable_type_without_key_paths(tmp_path: Path) -> None:
    """Matrix Row 9: Hive type auto undetected and no key_paths -> ValidationException."""
    hive_file = tmp_path / "UNKNOWN.DAT"
    hive_file.write_bytes(REGISTRY_MAGIC + b"\x00" * 4092)

    # Hive with no identifiable type or name
    mock_hive = create_mock_hive({}, hive_type=None, file_name=None)

    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = RegistryParserParameters(file_path=str(hive_file), hive_type="auto")

    with (
        patch("iryx.gateway.tools.registry_parser.RegistryHive", return_value=mock_hive),
        pytest.raises(ValidationException) as exc,
    ):
        await tool.execute(params, ctx)
    assert "Type de ruche non déterminable" in str(exc.value)


# --- Unit Tests: Search Query Filter & Fault Resilience ---


@pytest.mark.asyncio
async def test_search_query_filtering(tmp_path: Path) -> None:
    """Verify search_query filters values across keys, names, and data."""
    hive_file = tmp_path / "NTUSER.DAT"
    hive_file.write_bytes(REGISTRY_MAGIC + b"\x00" * 4092)

    val1 = make_mock_value("AppAlpha", "C:\\alpha.exe", "REG_SZ")
    val2 = make_mock_value("AppBeta", "C:\\malware\\beacon.exe", "REG_SZ")
    val3 = make_mock_value("MaliciousKeyName", "C:\\clean.exe", "REG_SZ")
    run_key = make_mock_key("Run", values=[val1, val2, val3])

    key_path = r"\Software\Microsoft\Windows\CurrentVersion\Run"
    mock_hive = create_mock_hive({key_path: run_key}, hive_type="ntuser")

    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())

    # Search for "malware" in value data
    params = RegistryParserParameters(
        file_path=str(hive_file),
        hive_type="ntuser",
        key_paths=[key_path],
        search_query="malware",
    )

    with patch("iryx.gateway.tools.registry_parser.RegistryHive", return_value=mock_hive):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["normalized_content"]["value_name"] == "AppBeta"


@pytest.mark.asyncio
async def test_isolated_corrupted_value_resilience(tmp_path: Path) -> None:
    """Verify parser isolates corrupted values and continues extracting valid ones."""
    hive_file = tmp_path / "NTUSER.DAT"
    hive_file.write_bytes(REGISTRY_MAGIC + b"\x00" * 4092)

    val_good1 = make_mock_value("Good1", "Data1", "REG_SZ")
    val_good2 = make_mock_value("Good2", "Data2", "REG_SZ")

    def generator_with_error():
        yield val_good1
        raise RuntimeError("Corrupted value cell")
        yield val_good2  # Unreachable

    key = MagicMock()
    key.name = "KeyWithCorruptedValue"
    key.header.last_modified = 132470000000000000
    key.values_count = 2
    key.iter_values.return_value = generator_with_error()
    key.iter_subkeys.return_value = None

    key_path = r"\Software\TestKey"
    mock_hive = create_mock_hive({key_path: key}, hive_type="ntuser")

    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = RegistryParserParameters(
        file_path=str(hive_file),
        hive_type="ntuser",
        key_paths=[key_path],
    )

    with patch("iryx.gateway.tools.registry_parser.RegistryHive", return_value=mock_hive):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["normalized_content"]["value_name"] == "Good1"
    assert len(result.metadata["errors"]) == 1
    assert "Corrupted value cell" in result.metadata["errors"][0]["error"]


# --- Integration Tests: ToolRunner with SQLite DB Persistence ---


@pytest.mark.asyncio
async def test_tool_runner_success_persistence(
    db_session: Session,
    test_case: Case,
    test_evidence: Evidence,
    tmp_path: Path,
) -> None:
    """Verify ToolRunner persists ToolExecution (success, sha256) and Observation rows."""
    hive_file = tmp_path / "NTUSER.DAT"
    hive_file.write_bytes(REGISTRY_MAGIC + b"\x00" * 4092)

    val = make_mock_value("PersistVal", "PersistenceCommand", "REG_SZ")
    key = make_mock_key("Run", values=[val], last_modified=132470000000000000)

    key_path = r"\Software\Microsoft\Windows\CurrentVersion\Run"
    mock_hive = create_mock_hive({key_path: key}, hive_type="ntuser")

    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(
        case_id=test_case.id,
        evidence_id=test_evidence.id,
        agent_role="Executor",
    )
    params = RegistryParserParameters(
        evidence_id=test_evidence.id,
        file_path=str(hive_file),
        hive_type="ntuser",
        key_paths=[key_path],
    )

    with patch("iryx.gateway.tools.registry_parser.RegistryHive", return_value=mock_hive):
        result = await runner.execute_tool("parse_registry", params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.tool_execution_id is not None
    assert result.result_sha256 is not None
    assert len(result.result_sha256) == 64

    # Verify ToolExecution persisted in SQLite
    execution = db_session.get(ToolExecution, result.tool_execution_id)
    assert execution is not None
    assert execution.tool_name == "parse_registry"
    assert execution.tool_version == "1.0.0"
    assert execution.agent_role == "Executor"
    assert execution.status == ToolExecutionStatus.SUCCESS
    assert execution.result_sha256 == result.result_sha256

    # Verify Observation persisted in SQLite
    observations = (
        db_session.query(Observation).filter(Observation.tool_execution_id == execution.id).all()
    )
    assert len(observations) == 1
    obs = observations[0]
    assert obs.case_id == test_case.id
    assert obs.source_id == test_evidence.id
    assert obs.tool_name == "parse_registry"
    assert obs.source_location == key_path
    obs_ts = obs.timestamp_utc
    if obs_ts.tzinfo is None:
        obs_ts = obs_ts.replace(tzinfo=UTC)
    assert obs_ts == datetime(2020, 10, 12, 18, 13, 20, tzinfo=UTC)
    assert obs.normalized_content["value_name"] == "PersistVal"
    assert obs.normalized_content["value_data"] == "PersistenceCommand"


@pytest.mark.asyncio
async def test_tool_runner_invalid_header_persists_error_status(
    db_session: Session,
    test_case: Case,
    test_evidence: Evidence,
    tmp_path: Path,
) -> None:
    """Verify ToolRunner persists ToolExecution with status=ERROR when hive header is corrupt."""
    bad_file = tmp_path / "corrupt.dat"
    bad_file.write_bytes(b"INVALID_HEADER_DATA" * 5)  # < 4096 bytes

    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(
        case_id=test_case.id,
        evidence_id=test_evidence.id,
        agent_role="Executor",
    )
    params = RegistryParserParameters(
        file_path=str(bad_file),
    )

    with pytest.raises(ToolExecutionFailedException):
        await runner.execute_tool("parse_registry", params, ctx)

    # ToolExecution must be persisted in SQLite with status=ERROR
    execution = (
        db_session.query(ToolExecution)
        .filter(ToolExecution.case_id == test_case.id)
        .order_by(ToolExecution.created_at.desc())
        .first()
    )
    assert execution is not None
    assert execution.tool_name == "parse_registry"
    assert execution.status == ToolExecutionStatus.ERROR
    assert execution.error_message is not None
    assert "Format de ruche de Registre non reconnu ou corrompu" in execution.error_message


@pytest.mark.asyncio
async def test_tool_runner_missing_source_no_persistence(
    db_session: Session,
    test_case: Case,
) -> None:
    """Verify ToolRunner does NOT persist ToolExecution on missing source (ValidationException)."""
    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)
    params = RegistryParserParameters(file_path="non_existent_file.hiv")

    with pytest.raises(ValidationException):
        await runner.execute_tool("parse_registry", params, ctx)

    executions = db_session.query(ToolExecution).filter(ToolExecution.case_id == test_case.id).all()
    assert len(executions) == 0


def test_default_registry_contains_registry_parser() -> None:
    """Verify default_registry includes RegistryParserTool automatically."""
    assert default_registry.has("parse_registry")
    tool = default_registry.get("parse_registry")
    assert isinstance(tool, RegistryParserTool)
    assert tool.name == "parse_registry"
    assert tool.version == "1.0.0"
    assert tool.timeout_seconds == 120


@pytest.mark.asyncio
async def test_scenario_auto_hive_type_detection_presets(
    test_case: Case,
    tmp_path: Path,
) -> None:
    """Verify auto-detection of hive type and resolution of default presets without key_paths."""
    # Create hive file with bare stem 'software'
    hive_file = tmp_path / "SOFTWARE"
    hive_file.write_bytes(REGISTRY_MAGIC + b"\x00" * 4092)

    val1 = make_mock_value("AppRun", "C:\\app.exe", "REG_SZ")
    run_key = make_mock_key(r"\Microsoft\Windows\CurrentVersion\Run", values=[val1])

    mock_hive = create_mock_hive({r"\Microsoft\Windows\CurrentVersion\Run": run_key})
    # internal hive properties
    mock_hive.hive_type = None
    mock_hive.name = "software"

    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=test_case.id)
    # hive_type="auto" by default, key_paths=None
    params = RegistryParserParameters(file_path=str(hive_file))

    with patch("iryx.gateway.tools.registry_parser.RegistryHive", return_value=mock_hive):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.raw_output["hive_type"] == "software"
    assert len(result.observations) == 1
    assert result.observations[0]["normalized_content"]["value_name"] == "AppRun"
    assert (
        result.observations[0]["normalized_content"]["key_path"]
        == r"\Microsoft\Windows\CurrentVersion\Run"
    )


@pytest.mark.asyncio
async def test_registry_parser_staging_directory_resolution(
    test_case: Case,
    tmp_path: Path,
) -> None:
    """Verify sealed evidence file resolution in staging path ({evidence_staging_path}/{id}.bin)."""
    evidence_id = uuid.uuid4()
    staged_file = tmp_path / f"{evidence_id}.bin"
    staged_file.write_bytes(REGISTRY_MAGIC + b"\x00" * 4092)

    val = make_mock_value("StagedVal", "Data", "REG_SZ")
    key = make_mock_key(r"\Software\Test", values=[val])
    mock_hive = create_mock_hive({r"\Software\Test": key})
    mock_hive.hive_type = "software"

    tool = RegistryParserTool()
    ctx = ToolExecutionContext(case_id=test_case.id)
    params = RegistryParserParameters(
        evidence_id=evidence_id,
        key_paths=[r"\Software\Test"],
    )

    mock_settings = MagicMock()
    mock_settings.evidence_staging_path = str(tmp_path)
    mock_settings.evidence_storage_path = str(tmp_path / "storage")

    with (
        patch("iryx.gateway.tools.registry_parser.get_settings", return_value=mock_settings),
        patch("iryx.gateway.tools.registry_parser.RegistryHive", return_value=mock_hive),
    ):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["source_id"] == evidence_id
    assert result.observations[0]["normalized_content"]["value_name"] == "StagedVal"


def test_edge_cases_post_review_patches() -> None:
    """Verify specific edge cases identified and patched during review triage."""
    # 1. Negative FILETIME handling
    assert filetime_to_utc(-1000) is None
    assert filetime_to_utc(0) is None

    # 2. Key path normalization: trailing backslash and redundant hive root prefixes
    assert normalize_key_path(r"HKLM\Software\Run\\") == r"\Software\Run"
    assert normalize_key_path(r"HKEY_LOCAL_MACHINE\Software\Microsoft") == r"\Software\Microsoft"
    assert normalize_key_path(r"HKCU\Software\Policies") == r"\Software\Policies"
    assert normalize_key_path(r"\\") == "\\"

    # 3. Value data normalization: datetime formatting and bytes in lists
    dt_val = datetime(2026, 11, 24, 18, 0, 0, tzinfo=UTC)
    norm_dt, trunc_dt = normalize_value_data(dt_val)
    assert norm_dt == "2026-11-24T18:00:00+00:00"
    assert not trunc_dt

    list_val = ["valid", b"\xde\xad\xbe\xef", 42]
    norm_list, trunc_list = normalize_value_data(list_val)
    assert norm_list == ["valid", "deadbeef", 42]
    assert not trunc_list

    # Long string truncation
    long_str = "A" * 5000
    norm_str, trunc_str = normalize_value_data(long_str)
    assert len(norm_str) == 4096
    assert trunc_str

    # 4. Search query None matching guard
    tool = RegistryParserTool()
    assert not tool._matches_search_query("none", r"\Key", "Val", None)
    assert tool._matches_search_query("none", r"\Key", "Val", "NoneOfString")
