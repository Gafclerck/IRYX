"""Unit tests for EvtxParserTool: EVTX parsing, UTC normalization, and ToolRunner integration."""

import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import Evtx.Evtx as evtx
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.analytics.models import Observation
from iryx.auth.models import Organization
from iryx.cases.models import Case
from iryx.core.config import get_settings
from iryx.core.exceptions import ValidationException
from iryx.db.base import Base
from iryx.evidence.models import Evidence
from iryx.gateway.base import ToolExecutionContext
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.gateway.registry import default_registry
from iryx.gateway.runner import ToolRunner
from iryx.gateway.tools.evtx_parser import (
    EVTX_MAGIC,
    EvtxParserParameters,
    EvtxParserTool,
    _local_tag,
    _parse_event_timestamp,
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
    org = Organization(name="CERT EVTX Test")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Analyse EVTX")
    db_session.add(case)
    db_session.commit()
    return case


@pytest.fixture
def test_evidence(db_session: Session, test_case: Case) -> Evidence:
    """Provide a persisted test Evidence entity."""
    evidence = Evidence(
        case_id=test_case.id,
        original_name="Security.evtx",
        file_size=65536,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    db_session.add(evidence)
    db_session.commit()
    return evidence


def make_event_xml(
    event_id: int = 4624,
    record_id: int | None = 1001,
    channel: str = "Security",
    computer: str = "WIN-SRV-01.corp.local",
    provider: str = "Microsoft-Windows-Security-Auditing",
    time_created: str = "2026-11-24T16:00:00.123456Z",
    level: int = 0,
    opcode: int = 0,
    task: int = 12544,
    keywords: str = "0x8020000000000000",
    process_id: int | None = 4,
    thread_id: int | None = 12,
    user_id: str | None = "S-1-5-18",
    activity_id: str | None = "{12345678-1234-1234-1234-123456789abc}",
    event_data: dict[str, str] | None = None,
) -> str:
    """Generate valid Windows Event XML string for testing."""
    data_xml = ""
    if event_data:
        for k, v in event_data.items():
            data_xml += f'<Data Name="{k}">{v}</Data>'

    record_elem = f"<EventRecordID>{record_id}</EventRecordID>" if record_id is not None else ""
    exec_elem = (
        f'<Execution ProcessID="{process_id}" ThreadID="{thread_id}"/>'
        if process_id is not None
        else ""
    )
    sec_elem = f'<Security UserID="{user_id}"/>' if user_id is not None else ""
    corr_elem = f'<Correlation ActivityID="{activity_id}"/>' if activity_id is not None else ""

    return (
        f'<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">'
        f"<System>"
        f'<Provider Name="{provider}"/>'
        f"<EventID>{event_id}</EventID>"
        f"<Level>{level}</Level>"
        f"<Task>{task}</Task>"
        f"<Opcode>{opcode}</Opcode>"
        f"<Keywords>{keywords}</Keywords>"
        f'<TimeCreated SystemTime="{time_created}"/>'
        f"{record_elem}"
        f"{corr_elem}"
        f"{exec_elem}"
        f"<Channel>{channel}</Channel>"
        f"<Computer>{computer}</Computer>"
        f"{sec_elem}"
        f"</System>"
        f"<EventData>{data_xml}</EventData>"
        f"</Event>"
    )


def create_mock_evtx(records: list[Any]) -> MagicMock:
    """Create a mock evtx.Evtx context manager returning the given records."""
    mock_chunk = MagicMock()
    mock_chunk.records.return_value = iter(records)

    mock_evtx = MagicMock()
    mock_evtx.get_file_header.return_value.check_magic.return_value = True
    mock_evtx.chunks.return_value = [mock_chunk]
    mock_evtx.__enter__.return_value = mock_evtx
    mock_evtx.__exit__.return_value = None
    return mock_evtx


def create_mock_record(
    xml_str: str,
    record_num: int | None = 1001,
    offset: int = 4096,
    timestamp: datetime | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    """Create a mock Record instance."""
    record = MagicMock()
    if record_num is not None:
        record.record_num.return_value = record_num
    else:
        record.record_num.side_effect = AttributeError("No record_num")
    record.offset.return_value = offset
    record.timestamp.return_value = timestamp
    if side_effect:
        record.xml.side_effect = side_effect
    else:
        record.xml.return_value = xml_str
    return record


# --- Unit Tests: Parameters Schema Validation ---


def test_evtx_parameters_validation() -> None:
    """Verify EvtxParserParameters validates sources, time boundaries, and forbidden fields."""
    # 1. Missing both evidence_id and file_path
    with pytest.raises(ValidationError) as exc:
        EvtxParserParameters()
    assert "Au moins une source de données doit être fournie" in str(exc.value)

    # 2. Valid with file_path
    p1 = EvtxParserParameters(file_path="Security.evtx")
    assert p1.file_path == "Security.evtx"
    assert p1.max_records == 5000

    # 3. Timezone normalization on naive datetimes
    dt_naive = datetime(2026, 11, 24, 10, 0, 0)
    p2 = EvtxParserParameters(file_path="Security.evtx", start_time=dt_naive)
    assert p2.start_time is not None
    assert p2.start_time.tzinfo == UTC
    assert p2.start_time == datetime(2026, 11, 24, 10, 0, 0, tzinfo=UTC)

    # 4. Inconsistent time interval (start > end)
    with pytest.raises(ValidationError) as exc_time:
        EvtxParserParameters(
            file_path="Security.evtx",
            start_time=datetime(2026, 11, 24, 16, 0, 0, tzinfo=UTC),
            end_time=datetime(2026, 11, 24, 10, 0, 0, tzinfo=UTC),
        )
    assert "start_time" in str(exc_time.value)

    # 5. Extra fields forbidden
    with pytest.raises(ValidationError):
        EvtxParserParameters.model_validate({"file_path": "Security.evtx", "unknown_param": 123})


def test_local_tag_guard() -> None:
    """Verify _local_tag safely handles string and non-string tag inputs."""
    assert _local_tag("{http://schema}Event") == "Event"
    assert _local_tag("System") == "System"
    assert _local_tag(None) == ""
    assert _local_tag(123) == ""
    assert _local_tag(object()) == ""


def test_parse_event_timestamp_normalization() -> None:
    """Verify timestamp parsing handles ISO-8601 with Z, lowercase z, offsets, and fallbacks."""
    # ISO with uppercase Z
    dt1 = _parse_event_timestamp("2026-11-24T16:00:00.123456Z")
    assert dt1 is not None
    assert dt1.tzinfo == UTC
    assert dt1.hour == 16

    # ISO with lowercase z
    dt1_z = _parse_event_timestamp("2026-11-24T16:00:00.123456z")
    assert dt1_z is not None
    assert dt1_z.tzinfo == UTC
    assert dt1_z.hour == 16

    # Space instead of T
    dt2 = _parse_event_timestamp("2026-11-24 16:00:00.123456Z")
    assert dt2 is not None
    assert dt2.tzinfo == UTC
    assert dt2.hour == 16

    # Positive offset (+02:00)
    dt3 = _parse_event_timestamp("2026-11-24T18:00:00+02:00")
    assert dt3 is not None
    assert dt3.tzinfo == UTC
    assert dt3.hour == 16

    # Fallback to datetime object
    dt_fallback = datetime(2026, 11, 24, 14, 0, 0)
    dt4 = _parse_event_timestamp(None, fallback_dt=dt_fallback)
    assert dt4 is not None
    assert dt4.tzinfo == UTC
    assert dt4.hour == 14


# --- Unit Tests: File Header & Source Resolution Validation ---


@pytest.mark.asyncio
async def test_evtx_missing_file(tmp_path: Path) -> None:
    """Verify ValidationException is raised when file_path does not exist."""
    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(file_path=str(tmp_path / "non_existent.evtx"))

    with pytest.raises(ValidationException) as exc:
        await tool.execute(params, ctx)
    assert "introuvable" in str(exc.value)


@pytest.mark.asyncio
async def test_evtx_missing_evidence_id() -> None:
    """Verify ValidationException is raised when evidence_id is not staged."""
    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(evidence_id=uuid.uuid4())

    with pytest.raises(ValidationException) as exc:
        await tool.execute(params, ctx)
    assert "introuvable" in str(exc.value)


@pytest.mark.asyncio
async def test_evtx_invalid_header_non_evtx(tmp_path: Path) -> None:
    """Verify ValidationException is raised when file header is not EVTX magic (ElfFile\\x00)."""
    fake_file = tmp_path / "corrupt.evtx"
    fake_file.write_text("THIS IS NOT A VALID EVTX FILE" + "0" * 4100)

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(file_path=str(fake_file))

    with pytest.raises(ValidationException) as exc:
        await tool.execute(params, ctx)
    assert "Format EVTX non reconnu" in str(exc.value)


@pytest.mark.asyncio
async def test_evtx_truncated_header_under_4096_bytes(tmp_path: Path) -> None:
    """Verify ValidationException is raised when file is smaller than 4096 bytes."""
    truncated_file = tmp_path / "truncated.evtx"
    truncated_file.write_bytes(EVTX_MAGIC + b"\x00" * 100)

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(file_path=str(truncated_file))

    with pytest.raises(ValidationException) as exc:
        await tool.execute(params, ctx)
    assert "Format EVTX non reconnu" in str(exc.value)


@pytest.mark.asyncio
async def test_evtx_header_magic_check_failure(tmp_path: Path) -> None:
    """Verify ValidationException is raised when python-evtx check_magic fails."""
    evtx_file = tmp_path / "check_magic_fail.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    mock_evtx = MagicMock()
    mock_evtx.get_file_header.return_value.check_magic.return_value = False
    mock_evtx.__enter__.return_value = mock_evtx
    mock_evtx.__exit__.return_value = None

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(file_path=str(evtx_file))

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx), pytest.raises(ValidationException) as exc:
        await tool.execute(params, ctx)
    assert "Format EVTX non reconnu" in str(exc.value)


# --- Unit Tests: Nominal EVTX Parsing & Observations Extraction ---


@pytest.mark.asyncio
async def test_evtx_nominal_parsing(tmp_path: Path) -> None:
    """Verify nominal extraction of Security events (4624 Logon & 4625 Failed Logon)."""
    evtx_file = tmp_path / "Security.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    xml_4624 = make_event_xml(
        event_id=4624,
        record_id=101,
        channel="Security",
        computer="DC01.corp.local",
        provider="Microsoft-Windows-Security-Auditing",
        time_created="2026-11-24T16:00:00.123456Z",
        level=0,
        opcode=1,
        task=12544,
        keywords="0x8020000000000000",
        process_id=4,
        thread_id=12,
        user_id="S-1-5-18",
        activity_id="{12345678-1234-1234-1234-123456789abc}",
        event_data={
            "TargetUserName": "admin_audit",
            "TargetDomainName": "CORP",
            "LogonType": "2",
        },
    )
    xml_4625 = make_event_xml(
        event_id=4625,
        record_id=102,
        channel="Security",
        computer="DC01.corp.local",
        provider="Microsoft-Windows-Security-Auditing",
        time_created="2026-11-24T16:05:00.654321Z",
        event_data={
            "TargetUserName": "attacker",
            "TargetDomainName": "CORP",
            "Status": "0xC000006D",
        },
    )

    rec1 = create_mock_record(xml_4624, record_num=101)
    rec2 = create_mock_record(xml_4625, record_num=102)
    mock_evtx = create_mock_evtx([rec1, rec2])

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4(), evidence_id=uuid.uuid4())
    params = EvtxParserParameters(file_path=str(evtx_file))

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2
    assert result.metadata["parsed_records_count"] == 2
    assert result.metadata["truncated"] is False
    assert result.metadata["errors"] == []

    # Check Observation 1 (4624)
    obs1 = result.observations[0]
    assert obs1["source_id"] == ctx.evidence_id
    assert obs1["source_location"] == "record_id:101"
    assert obs1["timestamp_utc"] == datetime(2026, 11, 24, 16, 0, 0, 123456, tzinfo=UTC)
    content1 = obs1["normalized_content"]
    assert content1["event_id"] == 4624
    assert content1["record_id"] == 101
    assert content1["channel"] == "Security"
    assert content1["computer"] == "DC01.corp.local"
    assert content1["provider_name"] == "Microsoft-Windows-Security-Auditing"
    assert content1["level"] == 0
    assert content1["opcode"] == 1
    assert content1["task"] == 12544
    assert content1["keywords"] == "0x8020000000000000"
    assert content1["process_id"] == 4
    assert content1["thread_id"] == 12
    assert content1["user_id"] == "S-1-5-18"
    assert content1["activity_id"] == "{12345678-1234-1234-1234-123456789abc}"
    assert content1["time_created_utc"] == "2026-11-24T16:00:00.123456+00:00"
    assert content1["event_data"]["TargetUserName"] == "admin_audit"
    assert content1["event_data"]["LogonType"] == "2"

    # Check Observation 2 (4625)
    obs2 = result.observations[1]
    assert obs2["source_location"] == "record_id:102"
    content2 = obs2["normalized_content"]
    assert content2["event_id"] == 4625
    assert content2["event_data"]["TargetUserName"] == "attacker"

    # Check raw_output format
    assert result.raw_output["records_count"] == 2
    assert len(result.raw_output["events"]) == 2
    assert result.raw_output["events"][0]["event_id"] == 4624
    assert result.raw_output["events"][0]["data"]["TargetUserName"] == "admin_audit"


# --- Unit Tests: Filtering Capabilities ---


@pytest.mark.asyncio
async def test_evtx_filter_event_ids(tmp_path: Path) -> None:
    """Verify filtering by event_ids extracts only requested Event IDs."""
    evtx_file = tmp_path / "Security.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    rec1 = create_mock_record(make_event_xml(event_id=4624, record_id=1), record_num=1)
    rec2 = create_mock_record(make_event_xml(event_id=4625, record_id=2), record_num=2)
    rec3 = create_mock_record(make_event_xml(event_id=4688, record_id=3), record_num=3)
    rec4 = create_mock_record(make_event_xml(event_id=7045, record_id=4), record_num=4)
    mock_evtx = create_mock_evtx([rec1, rec2, rec3, rec4])

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(
        file_path=str(evtx_file),
        event_ids=[4625, 4688],
    )

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2
    extracted_ids = [obs["normalized_content"]["event_id"] for obs in result.observations]
    assert extracted_ids == [4625, 4688]


@pytest.mark.asyncio
async def test_evtx_filter_channels(tmp_path: Path) -> None:
    """Verify filtering by channels extracts only events from specified channels."""
    evtx_file = tmp_path / "System_and_Security.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    rec1 = create_mock_record(
        make_event_xml(event_id=4624, channel="Security", record_id=1), record_num=1
    )
    rec2 = create_mock_record(
        make_event_xml(event_id=7045, channel="System", record_id=2), record_num=2
    )
    rec3 = create_mock_record(
        make_event_xml(
            event_id=4104,
            channel="Microsoft-Windows-PowerShell/Operational",
            record_id=3,
        ),
        record_num=3,
    )
    mock_evtx = create_mock_evtx([rec1, rec2, rec3])

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(
        file_path=str(evtx_file),
        channels=["security", "system"],
    )

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2
    extracted_channels = [obs["normalized_content"]["channel"] for obs in result.observations]
    assert "Security" in extracted_channels
    assert "System" in extracted_channels


@pytest.mark.asyncio
async def test_evtx_filter_time_window(tmp_path: Path) -> None:
    """Verify filtering by temporal window retains only events within start_time and end_time."""
    evtx_file = tmp_path / "Security.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    rec1 = create_mock_record(
        make_event_xml(record_id=1, time_created="2026-11-24T08:00:00Z"), record_num=1
    )
    rec2 = create_mock_record(
        make_event_xml(record_id=2, time_created="2026-11-24T12:00:00Z"), record_num=2
    )
    rec3 = create_mock_record(
        make_event_xml(record_id=3, time_created="2026-11-24T14:30:00Z"), record_num=3
    )
    rec4 = create_mock_record(
        make_event_xml(record_id=4, time_created="2026-11-24T20:00:00Z"), record_num=4
    )
    mock_evtx = create_mock_evtx([rec1, rec2, rec3, rec4])

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(
        file_path=str(evtx_file),
        start_time=datetime(2026, 11, 24, 10, 0, 0, tzinfo=UTC),
        end_time=datetime(2026, 11, 24, 16, 0, 0, tzinfo=UTC),
    )

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2
    record_ids = [obs["normalized_content"]["record_id"] for obs in result.observations]
    assert record_ids == [2, 3]


@pytest.mark.asyncio
async def test_evtx_filter_search_query(tmp_path: Path) -> None:
    """Verify search_query matches text against field values, not ubiquitous XML tag markup."""
    evtx_file = tmp_path / "Security.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    rec1 = create_mock_record(
        make_event_xml(
            event_id=4688,
            record_id=1,
            event_data={"NewProcessName": "C:\\Windows\\System32\\cmd.exe"},
        ),
        record_num=1,
    )
    rec2 = create_mock_record(
        make_event_xml(
            event_id=4688,
            record_id=2,
            event_data={
                "NewProcessName": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe"
            },
        ),
        record_num=2,
    )
    rec3 = create_mock_record(
        make_event_xml(
            event_id=4624,
            record_id=3,
            computer="POWERSHELL-TEST-SRV",
        ),
        record_num=3,
    )
    mock_evtx = create_mock_evtx([rec1, rec2, rec3])

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(
        file_path=str(evtx_file),
        search_query="powershell.exe",
    )

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["normalized_content"]["record_id"] == 2

    # Verify query for generic XML tag word like "system" does NOT match every record blindly
    params_system = EvtxParserParameters(
        file_path=str(evtx_file),
        search_query="non_existent_unique_token_xyz",
    )
    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result_empty = await tool.execute(params_system, ctx)
    assert len(result_empty.observations) == 0


# --- Unit Tests: Edge Cases, Corruption Resilience & Truncation ---


@pytest.mark.asyncio
async def test_evtx_empty_file_zero_records(tmp_path: Path) -> None:
    """Verify empty EVTX file (4096 bytes header, 0 records) with real python-evtx parser."""
    evtx_file = tmp_path / "empty_real.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(file_path=str(evtx_file))

    # Executed WITHOUT mocking Evtx.Evtx to test genuine python-evtx interaction
    result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.observations == []
    assert result.metadata["parsed_records_count"] == 0
    assert result.metadata["truncated"] is False
    assert result.metadata["errors"] == []


@pytest.mark.asyncio
async def test_evtx_unnamed_data_tags_collision_prevention(tmp_path: Path) -> None:
    """Verify parsing 3+ unnamed <Data> tags correctly creates Data, Data_1, Data_2."""
    evtx_file = tmp_path / "unnamed_data.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    xml_with_unnamed_data = (
        '<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">'
        "<System>"
        "<EventID>1000</EventID>"
        "<EventRecordID>42</EventRecordID>"
        "<Channel>Application</Channel>"
        "<Computer>APP-SRV</Computer>"
        "</System>"
        "<EventData>"
        "<Data>First Value</Data>"
        "<Data>Second Value</Data>"
        "<Data>Third Value</Data>"
        "<Data>Fourth Value</Data>"
        "</EventData>"
        "</Event>"
    )

    rec = create_mock_record(xml_with_unnamed_data, record_num=42)
    mock_evtx = create_mock_evtx([rec])

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(file_path=str(evtx_file))

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    event_data = result.observations[0]["normalized_content"]["event_data"]
    assert event_data["Data"] == "First Value"
    assert event_data["Data_1"] == "Second Value"
    assert event_data["Data_2"] == "Third Value"
    assert event_data["Data_3"] == "Fourth Value"


@pytest.mark.asyncio
async def test_evtx_record_offset_fallback_when_no_record_id(tmp_path: Path) -> None:
    """Verify fallback to record_offset:{offset} when EventRecordID is absent."""
    evtx_file = tmp_path / "no_record_id.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    xml_no_record_id = make_event_xml(event_id=999, record_id=None)
    rec = create_mock_record(xml_no_record_id, record_num=None, offset=8192)
    mock_evtx = create_mock_evtx([rec])

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(file_path=str(evtx_file))

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    obs = result.observations[0]
    assert obs["source_location"] == "record_offset:8192"
    assert obs["normalized_content"]["record_id"] == 8192


@pytest.mark.asyncio
async def test_evtx_lazy_chunk_corruption_resilience(tmp_path: Path) -> None:
    """Verify that a corrupted chunk header does not abort subsequent valid chunks."""
    evtx_file = tmp_path / "chunk_corrupt.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    # Chunk 1 is corrupted and chunk.records() raises ParseException
    mock_chunk1 = MagicMock()
    mock_chunk1.records.side_effect = evtx.ParseException("Corrupted chunk 1")

    # Chunk 2 is valid with 2 records
    rec1 = create_mock_record(make_event_xml(event_id=4624, record_id=201), record_num=201)
    rec2 = create_mock_record(make_event_xml(event_id=4624, record_id=202), record_num=202)
    mock_chunk2 = MagicMock()
    mock_chunk2.records.return_value = iter([rec1, rec2])

    mock_evtx = MagicMock()
    mock_evtx.get_file_header.return_value.check_magic.return_value = True
    mock_evtx.chunks.return_value = iter([mock_chunk1, mock_chunk2])
    mock_evtx.__enter__.return_value = mock_evtx
    mock_evtx.__exit__.return_value = None

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(file_path=str(evtx_file))

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    # Chunk 2 records are preserved!
    assert len(result.observations) == 2
    assert len(result.metadata["errors"]) == 1
    assert "Corrupted chunk 1" in result.metadata["errors"][0]["error"]


@pytest.mark.asyncio
async def test_evtx_corrupted_record_resilience(tmp_path: Path) -> None:
    """Verify parser recovers from corrupted records (InvalidRecordException / XML error)."""
    evtx_file = tmp_path / "corrupted_records.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    records = []
    for i in range(1, 51):
        if i == 25:
            rec = create_mock_record(
                xml_str="",
                record_num=25,
                offset=25000,
                side_effect=evtx.InvalidRecordException(),
            )
        elif i == 30:
            rec = create_mock_record(
                xml_str="<Event><System><UnclosedTag></System></Event>",
                record_num=30,
                offset=30000,
            )
        else:
            rec = create_mock_record(
                xml_str=make_event_xml(event_id=4624, record_id=i),
                record_num=i,
                offset=i * 1000,
            )
        records.append(rec)

    mock_evtx = create_mock_evtx(records)

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(file_path=str(evtx_file))

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 48
    assert len(result.metadata["errors"]) == 2
    assert result.metadata["errors"][0]["record_id"] == 25
    assert result.metadata["errors"][1]["record_id"] == 30


@pytest.mark.asyncio
async def test_evtx_max_records_truncation(tmp_path: Path) -> None:
    """Verify parser enforces max_records ceiling and flags truncated=True."""
    evtx_file = tmp_path / "large.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    records = [
        create_mock_record(make_event_xml(event_id=4624, record_id=i), record_num=i)
        for i in range(1, 101)
    ]
    mock_evtx = create_mock_evtx(records)

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(file_path=str(evtx_file), max_records=20)

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 20
    assert result.metadata["parsed_records_count"] == 20
    assert result.metadata["truncated"] is True


@pytest.mark.asyncio
async def test_evtx_user_data_extraction(tmp_path: Path) -> None:
    """Verify extraction of key-value pairs from <UserData> blocks."""
    evtx_file = tmp_path / "user_data.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    user_data_xml = (
        '<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">'
        "<System>"
        '<Provider Name="Custom-App"/>'
        "<EventID>100</EventID>"
        "<EventRecordID>501</EventRecordID>"
        '<TimeCreated SystemTime="2026-11-24T17:00:00Z"/>'
        "<Channel>Application</Channel>"
        "<Computer>APP-SRV</Computer>"
        "</System>"
        "<UserData>"
        "<AppEvent xmlns='http://schemas.app.com'>"
        "<SessionID>SESS-987</SessionID>"
        "<Operation>DB_EXPORT</Operation>"
        "</AppEvent>"
        "</UserData>"
        "</Event>"
    )

    rec = create_mock_record(user_data_xml, record_num=501)
    mock_evtx = create_mock_evtx([rec])

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=uuid.uuid4())
    params = EvtxParserParameters(file_path=str(evtx_file))

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    content = result.observations[0]["normalized_content"]
    assert content["event_data"]["SessionID"] == "SESS-987"
    assert content["event_data"]["Operation"] == "DB_EXPORT"


# --- Unit Tests: ToolRunner & SQLite Database Integration ---


@pytest.mark.asyncio
async def test_evtx_parser_tool_runner_integration(
    db_session: Session,
    test_case: Case,
    test_evidence: Evidence,
    tmp_path: Path,
) -> None:
    """Verify full end-to-end execution of EvtxParserTool via ToolRunner with DB persistence."""
    evtx_file = tmp_path / "Security.evtx"
    evtx_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    xml_4624 = make_event_xml(
        event_id=4624,
        record_id=2001,
        channel="Security",
        computer="DC01.corp.local",
        time_created="2026-11-24T16:20:00Z",
        event_data={"TargetUserName": "admin_db", "LogonType": "10"},
    )
    rec = create_mock_record(xml_4624, record_num=2001)
    mock_evtx = create_mock_evtx([rec])

    runner = ToolRunner(db=db_session)
    ctx = ToolExecutionContext(
        case_id=test_case.id,
        evidence_id=test_evidence.id,
        agent_role="Executor",
    )
    params = EvtxParserParameters(
        evidence_id=test_evidence.id,
        file_path=str(evtx_file),
    )

    with patch("Evtx.Evtx.Evtx", return_value=mock_evtx):
        result = await runner.execute_tool("parse_evtx", params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.tool_execution_id is not None
    assert result.result_sha256 is not None
    assert len(result.result_sha256) == 64

    # Verify ToolExecution persisted in SQLite DB
    execution = db_session.get(ToolExecution, result.tool_execution_id)
    assert execution is not None
    assert execution.tool_name == "parse_evtx"
    assert execution.tool_version == "1.0.0"
    assert execution.agent_role == "Executor"
    assert execution.status == ToolExecutionStatus.SUCCESS
    assert execution.duration_ms >= 0
    assert execution.result_sha256 == result.result_sha256

    # Verify Observation persisted in SQLite DB
    observations = (
        db_session.query(Observation).filter(Observation.tool_execution_id == execution.id).all()
    )
    assert len(observations) == 1
    obs = observations[0]
    assert obs.case_id == test_case.id
    assert obs.source_id == test_evidence.id
    assert obs.tool_name == "parse_evtx"
    assert obs.source_location == "record_id:2001"
    # SQLite returns naive datetime for UTC timestamps
    obs_ts = obs.timestamp_utc
    if obs_ts.tzinfo is None:
        obs_ts = obs_ts.replace(tzinfo=UTC)
    assert obs_ts == datetime(2026, 11, 24, 16, 20, 0, tzinfo=UTC)
    assert obs.normalized_content["event_id"] == 4624
    assert obs.normalized_content["record_id"] == 2001
    assert obs.normalized_content["event_data"]["TargetUserName"] == "admin_db"


def test_default_registry_contains_evtx_parser() -> None:
    """Verify default_registry includes EvtxParserTool automatically."""
    assert default_registry.has("parse_evtx")
    tool = default_registry.get("parse_evtx")
    assert isinstance(tool, EvtxParserTool)
    assert tool.name == "parse_evtx"
    assert tool.version == "1.0.0"
    assert tool.timeout_seconds == 180


@pytest.mark.asyncio
async def test_evtx_parser_staging_directory_resolution(
    db_session: Session,
    test_case: Case,
    tmp_path: Path,
) -> None:
    """Verify sealed evidence file resolution in staging path ({evidence_staging_path}/{id}.bin)."""
    evidence_id = uuid.uuid4()
    staged_file = tmp_path / f"{evidence_id}.bin"
    staged_file.write_bytes(EVTX_MAGIC + b"\x00" * 4088)

    rec = create_mock_record(make_event_xml(event_id=4624, record_id=777), record_num=777)
    mock_evtx = create_mock_evtx([rec])

    tool = EvtxParserTool()
    ctx = ToolExecutionContext(case_id=test_case.id)
    params = EvtxParserParameters(evidence_id=evidence_id)

    mock_settings = MagicMock()
    mock_settings.evidence_staging_path = str(tmp_path)
    mock_settings.evidence_storage_path = str(tmp_path / "storage")

    with (
        patch("iryx.gateway.tools.evtx_parser.get_settings", return_value=mock_settings),
        patch("Evtx.Evtx.Evtx", return_value=mock_evtx),
    ):
        result = await tool.execute(params, ctx)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["source_id"] == evidence_id
    assert result.observations[0]["source_location"] == "record_id:777"
