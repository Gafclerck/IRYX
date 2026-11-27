"""Unit tests for Volatility3Tool: memory forensics in air-gapped mode with ISF symbols."""

import json
import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.analytics.models import Observation
from iryx.auth.models import Organization
from iryx.cases.models import Case
from iryx.core.config import get_settings
from iryx.core.exceptions import (
    PluginNotWhitelistedException,
    ToolExecutionFailedException,
    ToolExecutionTimeoutException,
    ValidationException,
)
from iryx.db.base import Base
from iryx.evidence.models import Evidence
from iryx.gateway.base import ToolExecutionContext
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.gateway.registry import default_registry
from iryx.gateway.runner import ToolRunner
from iryx.gateway.tools.volatility_analyzer import (
    Volatility3Parameters,
    Volatility3Tool,
    VolatilityExecutionError,
    extract_tree_nodes,
    parse_utc_datetime,
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
    org = Organization(name="CERT Memory Analysis Test")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Forensique Mémoire Windows")
    db_session.add(case)
    db_session.commit()
    return case


@pytest.fixture
def test_evidence(db_session: Session, test_case: Case) -> Evidence:
    """Provide a persisted test Evidence entity for memory dumps."""
    evidence = Evidence(
        case_id=test_case.id,
        original_name="memdump.raw",
        file_size=1073741824,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    db_session.add(evidence)
    db_session.commit()
    return evidence


@pytest.fixture
def dummy_dump_file(tmp_path: Path) -> Path:
    """Create a dummy memory dump file."""
    f = tmp_path / "win7_x64.raw"
    f.write_bytes(b"\x00" * 4096)
    return f


# ---------------------------------------------------------------------------
# Unit tests: Helper Functions
# ---------------------------------------------------------------------------


def test_parse_utc_datetime() -> None:
    """Test datetime parsing into UTC."""
    assert parse_utc_datetime(None) is None
    assert parse_utc_datetime("") is None
    assert parse_utc_datetime("N/A") is None
    assert parse_utc_datetime("none") is None

    # ISO with Z
    dt_z = parse_utc_datetime("2026-11-24T20:30:00Z")
    assert dt_z == datetime(2026, 11, 24, 20, 30, 0, tzinfo=UTC)

    # ISO with +00:00
    dt_iso = parse_utc_datetime("2020-05-19T19:42:07+00:00")
    assert dt_iso == datetime(2020, 5, 19, 19, 42, 7, tzinfo=UTC)

    # Space separated
    dt_space = parse_utc_datetime("2020-05-19 19:42:07")
    assert dt_space == datetime(2020, 5, 19, 19, 42, 7, tzinfo=UTC)

    # Already datetime
    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert parse_utc_datetime(naive) == naive.replace(tzinfo=UTC)


def test_extract_tree_nodes() -> None:
    """Test recursive flattening of tree structures."""
    tree = [
        {
            "PID": 4,
            "ImageFileName": "System",
            "__children": [
                {
                    "PID": 256,
                    "ImageFileName": "smss.exe",
                    "__children": [
                        {"PID": 368, "ImageFileName": "csrss.exe", "__children": []},
                    ],
                }
            ],
        },
        {"PID": 500, "ImageFileName": "explorer.exe", "__children": []},
    ]
    flat = extract_tree_nodes(tree)
    pids = [n["PID"] for n in flat]
    assert pids == [4, 256, 368, 500]


# ---------------------------------------------------------------------------
# Unit tests: Pydantic Validation & Registry Checks
# ---------------------------------------------------------------------------


def test_volatility_parameters_validation(dummy_dump_file: Path) -> None:
    """Test Volatility3Parameters schema constraints and validations."""
    # Valid
    params = Volatility3Parameters(
        file_path=str(dummy_dump_file),
        plugin_name="windows.info",
    )
    assert params.plugin_name == "windows.info"
    assert params.max_results == 5000
    assert params.plugin_args == []

    # Missing both sources
    with pytest.raises(ValidationError):
        Volatility3Parameters(plugin_name="windows.info")

    # Extra attributes forbidden
    with pytest.raises(ValidationError):
        Volatility3Parameters(
            file_path=str(dummy_dump_file),
            plugin_name="windows.info",
            extra_field="disallowed",
        )

    # Invalid max_results
    with pytest.raises(ValidationError):
        Volatility3Parameters(
            file_path=str(dummy_dump_file),
            plugin_name="windows.info",
            max_results=0,
        )


def test_registry_registration() -> None:
    """Verify analyze_memory registration in default_registry."""
    tool = default_registry.get("analyze_memory")
    assert isinstance(tool, Volatility3Tool)
    assert tool.name == "analyze_memory"
    assert tool.version == "2.7.0"
    assert tool.timeout_seconds == 600
    assert default_registry.is_whitelisted("analyze_memory")


# ---------------------------------------------------------------------------
# Unit tests: Plugin Whitelist Rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthorized_plugin_rejection_direct(dummy_dump_file: Path) -> None:
    """Verify unauthorized plugins are immediately rejected before command execution."""
    tool = Volatility3Tool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())

    for bad_plugin in ("windows.mimikatz", "linux.bash", "windows.hashdump", "custom.exploit"):
        params = Volatility3Parameters(
            file_path=str(dummy_dump_file),
            plugin_name=bad_plugin,
        )
        with pytest.raises(PluginNotWhitelistedException) as exc_info:
            await tool.execute(params, ctx)
        assert exc_info.value.code == "PLUGIN_NOT_WHITELISTED"
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_unauthorized_plugin_rejection_via_runner(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Verify ToolRunner re-raises PluginNotWhitelistedException without persisting record."""
    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)

    with pytest.raises(PluginNotWhitelistedException) as exc_info:
        await runner.execute_tool(
            "analyze_memory",
            {
                "file_path": str(dummy_dump_file),
                "plugin_name": "windows.mimikatz",
            },
            ctx,
        )
    assert exc_info.value.code == "PLUGIN_NOT_WHITELISTED"

    # Verify no execution or observation was recorded in DB
    executions = db_session.query(ToolExecution).filter_by(case_id=test_case.id).all()
    assert len(executions) == 0
    observations = db_session.query(Observation).filter_by(case_id=test_case.id).all()
    assert len(observations) == 0


# ---------------------------------------------------------------------------
# Unit tests: Nominal 5 Whitelisted Plugins Execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plugin_windows_info_nominal(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Test windows.info nominal execution and observation extraction."""
    mock_vol_output = [
        {"Variable": "Kernel Base", "Value": "0xf8000264d000"},
        {"Variable": "NT Build", "Value": "7601.24544.amd64fre.win7sp1_ldr_escrow.200102-1707"},
        {"Variable": "SystemTime", "Value": "2020-05-19T19:42:07+00:00"},
        {"Variable": "NtSystemRoot", "Value": "C:\\Windows"},
    ]

    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (0, json.dumps(mock_vol_output).encode("utf-8"), b"")

        result = await runner.execute_tool(
            "analyze_memory",
            {
                "file_path": str(dummy_dump_file),
                "plugin_name": "windows.info",
            },
            ctx,
        )

        # Verify command flags
        mock_run.assert_called_once()
        cmd_called = mock_run.call_args.kwargs["cmd"]
        assert "--offline" in cmd_called
        assert "-q" in cmd_called
        assert "-r" in cmd_called
        assert "json" in cmd_called
        assert "windows.info" in cmd_called

        # Verify fallback to default ISF symbols path
        from iryx.core.config import get_settings

        assert "-s" in cmd_called
        s_idx = cmd_called.index("-s")
        assert cmd_called[s_idx + 1] == get_settings().volatility_symbols_path
        assert result.metadata["symbols_path"] == get_settings().volatility_symbols_path

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.metadata["plugin_name"] == "windows.info"
    assert result.metadata["volatility_version"] == "2.7.0"
    assert len(result.observations) == 1

    obs = result.observations[0]
    content = obs["normalized_content"]
    assert content["kernel_base"] == "0xf8000264d000"
    assert "7601" in content["nt_build"]
    assert obs["timestamp_utc"] == datetime(2020, 5, 19, 19, 42, 7, tzinfo=UTC)

    # Verify DB persistence
    persisted_obs = db_session.query(Observation).filter_by(case_id=test_case.id).all()
    assert len(persisted_obs) == 1
    assert persisted_obs[0].normalized_content["kernel_base"] == "0xf8000264d000"
    assert persisted_obs[0].timestamp_utc.year == 2020

    exec_record = db_session.query(ToolExecution).filter_by(case_id=test_case.id).first()
    assert exec_record is not None
    assert exec_record.status == ToolExecutionStatus.SUCCESS
    assert exec_record.tool_name == "analyze_memory"


@pytest.mark.asyncio
async def test_plugin_windows_pslist_nominal(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Test windows.pslist nominal execution and process observations."""
    mock_vol_output = [
        {
            "PID": 4,
            "PPID": 0,
            "ImageFileName": "System",
            "Offset(V)": "0xfa8001633040",
            "Threads": 96,
            "Handles": 512,
            "SessionId": 0,
            "Wow64": False,
            "CreateTime": "2020-05-19T19:40:00+00:00",
            "ExitTime": None,
        },
        {
            "PID": 256,
            "PPID": 4,
            "ImageFileName": "smss.exe",
            "Offset(V)": "0xfa80026e6900",
            "Threads": 2,
            "Handles": 29,
            "SessionId": None,
            "Wow64": False,
            "CreateTime": "2020-05-19T19:40:01+00:00",
            "ExitTime": None,
        },
    ]

    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (0, json.dumps(mock_vol_output).encode("utf-8"), b"")

        result = await runner.execute_tool(
            "analyze_memory",
            {
                "file_path": str(dummy_dump_file),
                "plugin_name": "windows.pslist",
            },
            ctx,
        )

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2
    assert result.observations[0]["normalized_content"]["pid"] == 4
    assert result.observations[0]["normalized_content"]["image_file_name"] == "System"
    assert result.observations[0]["timestamp_utc"] == datetime(2020, 5, 19, 19, 40, 0, tzinfo=UTC)
    assert result.observations[1]["normalized_content"]["pid"] == 256
    assert result.observations[1]["normalized_content"]["image_file_name"] == "smss.exe"

    # Verify DB persistence
    persisted_obs = db_session.query(Observation).filter_by(case_id=test_case.id).all()
    assert len(persisted_obs) == 2


@pytest.mark.asyncio
async def test_plugin_windows_pstree_nominal(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Test windows.pstree hierarchical tree flattening."""
    mock_vol_output = [
        {
            "PID": 4,
            "PPID": 0,
            "ImageFileName": "System",
            "CreateTime": "2020-05-19T19:40:00+00:00",
            "__children": [
                {
                    "PID": 256,
                    "PPID": 4,
                    "ImageFileName": "smss.exe",
                    "CreateTime": "2020-05-19T19:40:01+00:00",
                    "__children": [],
                }
            ],
        }
    ]

    tool = Volatility3Tool()
    ctx = ToolExecutionContext(case_id=test_case.id)
    params = Volatility3Parameters(
        file_path=str(dummy_dump_file),
        plugin_name="windows.pstree",
    )

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (0, json.dumps(mock_vol_output).encode("utf-8"), b"")
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2
    assert [o["normalized_content"]["pid"] for o in result.observations] == [4, 256]


@pytest.mark.asyncio
async def test_plugin_windows_cmdline_nominal(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Test windows.cmdline command line arguments extraction."""
    mock_vol_output = [
        {"PID": 4, "Process": "System", "Args": None},
        {
            "PID": 1337,
            "Process": "powershell.exe",
            "Args": "powershell.exe -NoP -NonI -W Hidden -Enc SQBFAFgA",
        },
    ]

    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (0, json.dumps(mock_vol_output).encode("utf-8"), b"")

        result = await runner.execute_tool(
            "analyze_memory",
            {
                "file_path": str(dummy_dump_file),
                "plugin_name": "windows.cmdline",
            },
            ctx,
        )

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2
    ps_obs = [o for o in result.observations if o["normalized_content"]["pid"] == 1337][0]
    assert ps_obs["normalized_content"]["process_name"] == "powershell.exe"
    assert "SQBFAFgA" in ps_obs["normalized_content"]["args"]


@pytest.mark.asyncio
async def test_plugin_windows_netscan_nominal(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Test windows.netscan network sockets extraction with UTC timestamps."""
    mock_vol_output = [
        {
            "Offset": "0xfa8002bb03b0",
            "Proto": "TCPv4",
            "LocalAddr": "192.168.1.100",
            "LocalPort": 49152,
            "ForeignAddr": "185.190.140.2",
            "ForeignPort": 443,
            "State": "ESTABLISHED",
            "PID": 1337,
            "Owner": "powershell.exe",
            "Created": "2020-05-19T19:45:10+00:00",
        },
        {
            "Offset": "0xfa8002bb14c0",
            "Proto": "UDPv4",
            "LocalAddr": "0.0.0.0",
            "LocalPort": 53,
            "ForeignAddr": "*",
            "ForeignPort": 0,
            "State": "LISTENING",
            "PID": 420,
            "Owner": "dns.exe",
            "Created": None,
        },
    ]

    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (0, json.dumps(mock_vol_output).encode("utf-8"), b"")

        result = await runner.execute_tool(
            "analyze_memory",
            {
                "file_path": str(dummy_dump_file),
                "plugin_name": "windows.netscan",
            },
            ctx,
        )

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2

    tcp_obs = result.observations[0]
    assert tcp_obs["normalized_content"]["local_addr"] == "192.168.1.100"
    assert tcp_obs["normalized_content"]["foreign_addr"] == "185.190.140.2"
    assert tcp_obs["normalized_content"]["foreign_port"] == 443
    assert tcp_obs["timestamp_utc"] == datetime(2020, 5, 19, 19, 45, 10, tzinfo=UTC)


@pytest.mark.asyncio
async def test_plugin_windows_malfind_nominal(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Test windows.malfind code injection detection."""
    mock_vol_output = [
        {
            "PID": 1337,
            "Process": "powershell.exe",
            "Start VPN": "0x20000",
            "End VPN": "0x30000",
            "Tag": "VadS",
            "Protection": "PAGE_EXECUTE_READWRITE",
            "CommitCharge": 1,
            "PrivateMemory": 1,
            "Notes": None,
            "Hexdump": "4d 5a 90 00 03 00 00 00",
            "Disasm": "pop edx\ndec esp\ninc ebp",
        }
    ]

    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (0, json.dumps(mock_vol_output).encode("utf-8"), b"")

        result = await runner.execute_tool(
            "analyze_memory",
            {
                "file_path": str(dummy_dump_file),
                "plugin_name": "windows.malfind",
            },
            ctx,
        )

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    obs = result.observations[0]
    assert obs["normalized_content"]["protection"] == "PAGE_EXECUTE_READWRITE"
    assert "4d 5a" in obs["normalized_content"]["hexdump"]
    assert "pop edx" in obs["normalized_content"]["disasm"]


@pytest.mark.asyncio
async def test_plugin_alias_windows_malware_malfind(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Test that alias windows.malware.malfind maps to windows.malfind."""
    tool = Volatility3Tool()
    ctx = ToolExecutionContext(case_id=test_case.id)
    params = Volatility3Parameters(
        file_path=str(dummy_dump_file),
        plugin_name="windows.malware.malfind",
    )

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (0, b"[]", b"")
        result = await tool.execute(params, ctx)
        mock_run.assert_called_once()
        cmd = mock_run.call_args.kwargs["cmd"]
        assert "windows.malfind" in cmd

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.metadata["plugin_name"] == "windows.malfind"


# ---------------------------------------------------------------------------
# Unit tests: Options, Symbols, Args and Truncation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_custom_symbols_path_and_plugin_args(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Verify custom symbols_path and plugin_args are passed to subprocess."""
    tool = Volatility3Tool()
    ctx = ToolExecutionContext(case_id=test_case.id)
    params = Volatility3Parameters(
        file_path=str(dummy_dump_file),
        plugin_name="windows.pslist",
        symbols_path="/custom/isf/symbols",
        plugin_args=["--pid", "1234"],
    )

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (0, b"[]", b"")
        await tool.execute(params, ctx)

        cmd = mock_run.call_args.kwargs["cmd"]
        # Check custom symbols
        s_idx = cmd.index("-s")
        assert cmd[s_idx + 1] == "/custom/isf/symbols"
        # Check plugin args appended after plugin
        p_idx = cmd.index("windows.pslist")
        assert cmd[p_idx + 1 :] == ["--pid", "1234"]


@pytest.mark.asyncio
async def test_max_results_truncation(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Verify observation capping and truncation flag when exceeding max_results."""
    many_procs = [
        {
            "PID": i,
            "PPID": 4,
            "ImageFileName": f"proc_{i}.exe",
            "CreateTime": "2020-05-19T19:40:00+00:00",
        }
        for i in range(10)
    ]

    tool = Volatility3Tool()
    ctx = ToolExecutionContext(case_id=test_case.id)
    params = Volatility3Parameters(
        file_path=str(dummy_dump_file),
        plugin_name="windows.pslist",
        max_results=3,
    )

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (0, json.dumps(many_procs).encode("utf-8"), b"")
        result = await tool.execute(params, ctx)

    assert len(result.observations) == 3
    assert result.metadata["total_records"] == 10
    assert result.metadata["truncated"] is True


# ---------------------------------------------------------------------------
# Unit tests: Error Handling (Corrupted Dump, Malformed JSON, Timeout, Missing Source)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_corrupted_memory_dump_error(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Verify corrupted memory image leads to VolatilityExecutionError and error status."""
    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (
            1,
            b"Volatility 3 Framework 2.7.0\n",
            b"Unable to validate the plugin requirements: Unsatisfied requirement layer_name",
        )

        with pytest.raises(ToolExecutionFailedException) as exc_info:
            await runner.execute_tool(
                "analyze_memory",
                {
                    "file_path": str(dummy_dump_file),
                    "plugin_name": "windows.info",
                },
                ctx,
            )
        assert "Unsatisfied requirement" in str(exc_info.value)

    exec_record = db_session.query(ToolExecution).filter_by(case_id=test_case.id).first()
    assert exec_record is not None
    assert exec_record.status == ToolExecutionStatus.ERROR
    assert "Unsatisfied requirement" in (exec_record.error_message or "")


@pytest.mark.asyncio
async def test_malformed_json_output(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Verify malformed JSON from Volatility raises VolatilityExecutionError."""
    tool = Volatility3Tool()
    ctx = ToolExecutionContext(case_id=test_case.id)
    params = Volatility3Parameters(
        file_path=str(dummy_dump_file),
        plugin_name="windows.pslist",
    )

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (0, b"NON_JSON_CORRUPTED_OUTPUT", b"")
        with pytest.raises(VolatilityExecutionError):
            await tool.execute(params, ctx)


@pytest.mark.asyncio
async def test_execution_timeout(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Verify execution timeout marks ToolExecution as TIMEOUT."""
    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.side_effect = ToolExecutionTimeoutException(
            "Command execution timed out after 600s"
        )

        with pytest.raises(ToolExecutionTimeoutException):
            await runner.execute_tool(
                "analyze_memory",
                {
                    "file_path": str(dummy_dump_file),
                    "plugin_name": "windows.pslist",
                },
                ctx,
            )

    exec_record = db_session.query(ToolExecution).filter_by(case_id=test_case.id).first()
    assert exec_record is not None
    assert exec_record.status == ToolExecutionStatus.TIMEOUT


@pytest.mark.asyncio
async def test_missing_source_validation(db_session: Session, test_case: Case) -> None:
    """Verify missing source raises ValidationException without persisting execution."""
    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)

    non_existent_file = "/tmp/does_not_exist_at_all.raw"

    with pytest.raises(ValidationException):
        await runner.execute_tool(
            "analyze_memory",
            {
                "file_path": non_existent_file,
                "plugin_name": "windows.info",
            },
            ctx,
        )

    exec_record = db_session.query(ToolExecution).filter_by(case_id=test_case.id).first()
    assert exec_record is None


@pytest.mark.asyncio
async def test_json_with_prefix_warning_log(
    db_session: Session, test_case: Case, dummy_dump_file: Path
) -> None:
    """Verify JSON output extraction is robust with bracketed prefix log lines."""
    mock_vol_output = [
        {"Variable": "Kernel Base", "Value": "0xf8000264d000"},
        {"Variable": "NT Build", "Value": "7601.24545.amd64fre.win7sp1_ldr_escrow.200102-1707"},
    ]
    raw_output_with_warning = (
        "[WARNING] volatility3.framework: Symbol table download disabled in offline mode.\n"
        "[INFO] volatility3.framework: Processing memory sample.\n"
        f"{json.dumps(mock_vol_output)}"
    )

    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)

    with patch(
        "iryx.gateway.tools.volatility_analyzer.run_command_safely",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.return_value = (0, raw_output_with_warning.encode("utf-8"), b"")

        result = await runner.execute_tool(
            "analyze_memory",
            {
                "file_path": str(dummy_dump_file),
                "plugin_name": "windows.info",
            },
            ctx,
        )

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["normalized_content"]["kernel_base"] == "0xf8000264d000"


@pytest.mark.asyncio
async def test_source_resolution_by_evidence_id_in_staging(
    db_session: Session, test_case: Case, test_evidence: Evidence, tmp_path: Path
) -> None:
    """Verify memory dump resolution using evidence_id and Observation.source_id linkage."""
    staging_file = tmp_path / f"{test_evidence.id}.raw"
    staging_file.write_bytes(b"\x00" * 4096)

    mock_vol_output = [
        {"Variable": "Kernel Base", "Value": "0xf8000264d000"},
        {"Variable": "NT Build", "Value": "7601"},
    ]

    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)

    from iryx.core.config import get_settings

    settings = get_settings()

    with (
        patch.object(settings, "evidence_staging_path", str(tmp_path)),
        patch(
            "iryx.gateway.tools.volatility_analyzer.run_command_safely",
            new_callable=AsyncMock,
        ) as mock_run,
    ):
        mock_run.return_value = (0, json.dumps(mock_vol_output).encode("utf-8"), b"")

        result = await runner.execute_tool(
            "analyze_memory",
            {
                "evidence_id": test_evidence.id,
                "plugin_name": "windows.info",
            },
            ctx,
        )

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    # Check Observation in DB has source_id == test_evidence.id
    db_obs = db_session.query(Observation).filter_by(case_id=test_case.id).first()
    assert db_obs is not None
    assert db_obs.source_id == test_evidence.id


@pytest.mark.asyncio
async def test_missing_evidence_id_raises_validation_exception(
    db_session: Session, test_case: Case
) -> None:
    """Verify non-existent evidence_id raises ValidationException without DB trace."""
    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(case_id=test_case.id)
    missing_id = uuid.uuid4()

    with pytest.raises(ValidationException) as exc_info:
        await runner.execute_tool(
            "analyze_memory",
            {
                "evidence_id": missing_id,
                "plugin_name": "windows.info",
            },
            ctx,
        )

    assert "Preuve introuvable" in str(exc_info.value)
    exec_record = db_session.query(ToolExecution).filter_by(case_id=test_case.id).first()
    assert exec_record is None
