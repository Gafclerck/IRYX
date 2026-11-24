"""Unit tests for LogCsvParserTool: formats, UTC normalization, and ToolRunner integration."""

import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.analytics.models import Observation
from iryx.auth.models import Organization
from iryx.cases.models import Case
from iryx.core.config import get_settings
from iryx.core.exceptions import NotFoundException, ValidationException
from iryx.db.base import Base
from iryx.evidence.models import Evidence
from iryx.gateway.base import ToolExecutionContext
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.gateway.registry import ToolRegistry, default_registry
from iryx.gateway.runner import ToolRunner
from iryx.gateway.tools.log_parser import (
    LogCsvParserParameters,
    LogCsvParserTool,
    parse_timestamp_to_utc,
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
    org = Organization(name="CERT LogParser Test")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Analyse Logs")
    db_session.add(case)
    db_session.commit()
    return case


@pytest.fixture
def test_evidence(db_session: Session, test_case: Case) -> Evidence:
    """Provide a persisted test Evidence entity."""
    evidence = Evidence(
        case_id=test_case.id,
        original_name="auth.log",
        file_size=1024,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    db_session.add(evidence)
    db_session.commit()
    return evidence


# --- Timestamp Normalization Unit Tests ---


def test_parse_timestamp_to_utc_formats() -> None:
    """Verify various timestamp patterns convert strictly to UTC timezone."""
    # ISO-8601 with Z
    dt1 = parse_timestamp_to_utc("2026-11-24T08:14:53Z")
    assert dt1 is not None
    assert dt1.tzinfo == UTC
    assert dt1 == datetime(2026, 11, 24, 8, 14, 53, tzinfo=UTC)

    # ISO-8601 with positive offset (+02:00)
    dt2 = parse_timestamp_to_utc("2026-11-24T10:14:53+02:00")
    assert dt2 is not None
    assert dt2.tzinfo == UTC
    assert dt2 == datetime(2026, 11, 24, 8, 14, 53, tzinfo=UTC)

    # CLF format (Apache/Nginx)
    dt3 = parse_timestamp_to_utc("24/Nov/2026:08:14:53 +0000")
    assert dt3 is not None
    assert dt3 == datetime(2026, 11, 24, 8, 14, 53, tzinfo=UTC)

    # Syslog BSD (infer current UTC year)
    dt4 = parse_timestamp_to_utc("Nov 24 08:14:53")
    assert dt4 is not None
    assert dt4.month == 11
    assert dt4.day == 24
    assert dt4.hour == 8
    assert dt4.minute == 14
    assert dt4.second == 53
    assert dt4.tzinfo == UTC
    assert dt4.year == datetime.now(UTC).year

    # Epoch unix timestamp in seconds
    dt5 = parse_timestamp_to_utc(1764000000)
    assert dt5 is not None
    assert dt5.tzinfo == UTC

    # Epoch unix timestamp in milliseconds
    dt6 = parse_timestamp_to_utc(1764000000000)
    assert dt6 is not None
    assert dt6.tzinfo == UTC
    assert dt6 == dt5

    # None and invalid string
    assert parse_timestamp_to_utc(None) is None
    assert parse_timestamp_to_utc("not-a-timestamp") is None


# --- Format Presets Unit Tests ---


@pytest.mark.asyncio
async def test_parse_csv_nominal() -> None:
    """Verify nominal CSV parsing with header and UTC timestamp conversion."""
    tool = LogCsvParserTool()
    csv_content = (
        "timestamp,ip,action,status\n"
        "2026-11-24T08:14:53Z,192.168.1.10,login,200\n"
        "2026-11-24T08:15:10Z,192.168.1.11,download,403\n"
    )
    params = LogCsvParserParameters(
        content=csv_content,
        format_preset="csv",
    )
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2
    assert result.metadata["parsed_records_count"] == 2
    assert result.metadata["errors"] == []

    obs1 = result.observations[0]
    assert obs1["timestamp_utc"] == datetime(2026, 11, 24, 8, 14, 53, tzinfo=UTC)
    assert obs1["source_location"] == "line:2"
    assert obs1["normalized_content"]["ip"] == "192.168.1.10"
    assert obs1["normalized_content"]["action"] == "login"
    assert obs1["normalized_content"]["status"] == "200"

    obs2 = result.observations[1]
    assert obs2["timestamp_utc"] == datetime(2026, 11, 24, 8, 15, 10, tzinfo=UTC)
    assert obs2["source_location"] == "line:3"
    assert obs2["normalized_content"]["action"] == "download"


@pytest.mark.asyncio
async def test_parse_apache_combined() -> None:
    """Verify Apache/Nginx combined log format parsing."""
    tool = LogCsvParserTool()
    log_content = (
        '192.168.1.10 - admin [24/Nov/2026:08:14:53 +0000] "GET /api HTTP/1.1" 200 1234 '
        '"https://example.com" "Mozilla/5.0"\n'
        '10.0.0.5 - - [24/Nov/2026:08:15:00 +0000] "POST /login HTTP/1.1" 401 543 '
        '"-" "curl/7.68.0"\n'
    )
    params = LogCsvParserParameters(
        content=log_content,
        format_preset="apache_combined",
    )
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2

    obs1 = result.observations[0]
    assert obs1["timestamp_utc"] == datetime(2026, 11, 24, 8, 14, 53, tzinfo=UTC)
    assert obs1["normalized_content"]["ip"] == "192.168.1.10"
    assert obs1["normalized_content"]["auth_user"] == "admin"
    assert obs1["normalized_content"]["method"] == "GET"
    assert obs1["normalized_content"]["path"] == "/api"
    assert obs1["normalized_content"]["status_code"] == 200
    assert obs1["normalized_content"]["bytes_sent"] == 1234
    assert obs1["normalized_content"]["user_agent"] == "Mozilla/5.0"


@pytest.mark.asyncio
async def test_parse_syslog_rfc3164_and_rfc5424() -> None:
    """Verify Syslog BSD (RFC 3164) and RFC 5424 parsing."""
    tool = LogCsvParserTool()
    log_content = (
        "Nov 24 08:14:53 srv-auth sshd[1234]: Accepted publickey for root from 192.168.1.5\n"
        "<165>1 2026-11-24T08:15:00.000Z srv-fw sudo 5678 ID42 - pam_unix(sudo:session): opened\n"
    )
    params = LogCsvParserParameters(
        content=log_content,
        format_preset="syslog",
    )
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2

    # RFC 3164 BSD
    obs1 = result.observations[0]
    assert obs1["timestamp_utc"].hour == 8
    assert obs1["timestamp_utc"].minute == 14
    assert obs1["normalized_content"]["hostname"] == "srv-auth"
    assert obs1["normalized_content"]["appname"] == "sshd"
    assert obs1["normalized_content"]["pid"] == "1234"
    assert "Accepted publickey" in obs1["normalized_content"]["message"]

    # RFC 5424
    obs2 = result.observations[1]
    assert obs2["timestamp_utc"] == datetime(2026, 11, 24, 8, 15, 0, tzinfo=UTC)
    assert obs2["normalized_content"]["hostname"] == "srv-fw"
    assert obs2["normalized_content"]["appname"] == "sudo"
    assert obs2["normalized_content"]["pid"] == "5678"


@pytest.mark.asyncio
async def test_parse_json_lines() -> None:
    """Verify JSON Lines parsing and fault tolerance on invalid JSON."""
    tool = LogCsvParserTool()
    ndjson_content = (
        '{"@timestamp": "2026-11-24T08:14:53Z", "src_ip": "192.168.1.10", "event": "connect"}\n'
        '{"time": "2026-11-24T08:15:00Z", "src_ip": "192.168.1.11", "event": "disconnect"}\n'
        "CORRUPTED_JSON_LINE_NOT_VALID_SYNTAX\n"
    )
    params = LogCsvParserParameters(
        content=ndjson_content,
        format_preset="json_lines",
    )
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2
    assert result.metadata["parsed_records_count"] == 2
    assert len(result.metadata["errors"]) == 1
    assert result.metadata["errors"][0]["line"] == 3

    obs1 = result.observations[0]
    assert obs1["timestamp_utc"] == datetime(2026, 11, 24, 8, 14, 53, tzinfo=UTC)
    assert obs1["normalized_content"]["src_ip"] == "192.168.1.10"
    assert obs1["normalized_content"]["event"] == "connect"


@pytest.mark.asyncio
async def test_parse_key_value() -> None:
    """Verify Key-Value firewall/WAF log parsing."""
    tool = LogCsvParserTool()
    kv_content = (
        'date=2026-11-24 time=08:14:53 devname="FW-01" srcip=192.168.1.10 dstip=10.0.0.1 '
        'action="deny" msg="Blocked exploit"\n'
        'timestamp="2026-11-24T08:15:00Z" srcip=192.168.1.20 action="allow"\n'
    )
    params = LogCsvParserParameters(
        content=kv_content,
        format_preset="key_value",
    )
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2

    obs1 = result.observations[0]
    assert obs1["timestamp_utc"] == datetime(2026, 11, 24, 8, 14, 53, tzinfo=UTC)
    assert obs1["normalized_content"]["srcip"] == "192.168.1.10"
    assert obs1["normalized_content"]["action"] == "deny"
    assert obs1["normalized_content"]["msg"] == "Blocked exploit"


@pytest.mark.asyncio
async def test_parse_custom_regex() -> None:
    """Verify custom regex format with named groups and UTC timestamp extraction."""
    tool = LogCsvParserTool()
    log_content = (
        "EVENT[2026-11-24T08:14:53Z] HOST(edge-router) MSG(Port scan detected)\n"
        "EVENT[2026-11-24T08:15:00Z] HOST(edge-router) MSG(SYN flood mitigated)\n"
    )
    regex_pattern = (
        r"^EVENT\[(?P<timestamp>[^\]]+)\] HOST\((?P<host>[^\)]+)\) MSG\((?P<message>[^\)]+)\)"
    )
    params = LogCsvParserParameters(
        content=log_content,
        format_preset="custom_regex",
        custom_regex=regex_pattern,
    )
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2

    obs1 = result.observations[0]
    assert obs1["timestamp_utc"] == datetime(2026, 11, 24, 8, 14, 53, tzinfo=UTC)
    assert obs1["normalized_content"]["host"] == "edge-router"
    assert "Port scan detected" in obs1["normalized_content"]["message"]


def test_invalid_custom_regex_raises_validation_exception() -> None:
    """Verify invalid regular expression syntax raises ValidationError."""
    with pytest.raises(ValidationError):
        LogCsvParserParameters(
            content="dummy line",
            format_preset="custom_regex",
            custom_regex="[invalid-regex(",
        )


# --- Error Tolerance and Fault Resilience ---


@pytest.mark.asyncio
async def test_fault_tolerance_corrupted_lines() -> None:
    """Verify file with 3 corrupted lines among 100 lines yields 97 observations and 3 errors."""
    tool = LogCsvParserTool()

    # Generate 100 lines: 97 valid Apache lines + 3 corrupted lines at indices 20, 50, 80
    lines: list[str] = []
    corrupted_indices = {20, 50, 80}
    for i in range(1, 101):
        if i in corrupted_indices:
            lines.append(f"MALFORMED_LINE_CORRUPTED_SYNTAX_{i}")
        else:
            sec = i % 60
            ip_last = i % 250
            lines.append(
                f"192.168.1.{ip_last} - - [24/Nov/2026:08:14:{sec:02d} +0000] "
                f'"GET /item/{i} HTTP/1.1" 200 500 "-" "Mozilla/5.0"'
            )

    content = "\n".join(lines)
    params = LogCsvParserParameters(
        content=content,
        format_preset="apache_combined",
    )
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 97
    assert result.metadata["parsed_records_count"] == 97
    assert len(result.metadata["errors"]) == 3
    assert {e["line"] for e in result.metadata["errors"]} == corrupted_indices


# --- Security and Command Injection Safety ---


@pytest.mark.asyncio
async def test_passive_security_command_injection_attempt() -> None:
    """Verify log content with shell metacharacters is treated as passive literal text."""
    tool = LogCsvParserTool()
    injection_content = (
        "192.168.1.10 - - [24/Nov/2026:08:14:53 +0000] "
        '"GET /api?cmd=;rm -rf /;$(whoami) HTTP/1.1" 200 100\n'
        "192.168.1.11 - - [24/Nov/2026:08:14:54 +0000] "
        '"GET /exec`cat /etc/passwd` HTTP/1.1" 403 0\n'
    )
    params = LogCsvParserParameters(
        content=injection_content,
        format_preset="apache_combined",
    )
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2

    obs1 = result.observations[0]
    assert ";rm -rf /;$(whoami)" in obs1["normalized_content"]["path"]
    assert obs1["normalized_content"]["status_code"] == 200

    obs2 = result.observations[1]
    assert "`cat /etc/passwd`" in obs2["normalized_content"]["path"]


# --- Empty File Handling ---


@pytest.mark.asyncio
async def test_empty_content_returns_zero_observations() -> None:
    """Verify empty content returns 0 observations, parsed_records_count = 0, and status SUCCESS."""
    tool = LogCsvParserTool()
    params = LogCsvParserParameters(
        content="",
        format_preset="auto",
    )
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 0
    assert result.metadata["parsed_records_count"] == 0
    assert result.metadata["total_lines"] == 0
    assert result.metadata["errors"] == []


# --- File Resolution and Missing Target Handling ---


@pytest.mark.asyncio
async def test_nonexistent_file_path_raises_not_found() -> None:
    """Verify nonexistent file_path raises ValidationException or NotFoundException."""
    tool = LogCsvParserTool()
    params = LogCsvParserParameters(
        file_path="/nonexistent/path/to/logfile.log",
        format_preset="auto",
    )
    context = ToolExecutionContext(case_id=uuid.uuid4())
    with pytest.raises((ValidationException, NotFoundException)):
        await tool.execute(params, context)


@pytest.mark.asyncio
async def test_nonexistent_evidence_id_raises_not_found(tmp_path: Path) -> None:
    """Verify missing evidence file on disk raises ValidationException or NotFoundException."""
    settings = get_settings()
    settings.evidence_staging_path = str(tmp_path / "staging")

    tool = LogCsvParserTool()
    fake_evidence_id = uuid.uuid4()
    params = LogCsvParserParameters(
        evidence_id=fake_evidence_id,
        format_preset="auto",
    )
    context = ToolExecutionContext(case_id=uuid.uuid4(), evidence_id=fake_evidence_id)
    with pytest.raises((ValidationException, NotFoundException)):
        await tool.execute(params, context)


@pytest.mark.asyncio
async def test_sealed_evidence_file_reading(tmp_path: Path) -> None:
    """Verify resolving sealed evidence from evidence_staging_path/{evidence_id}.bin."""
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    evidence_id = uuid.uuid4()
    bin_file = staging_dir / f"{evidence_id}.bin"
    bin_file.write_text(
        "timestamp,ip,action\n2026-11-24T08:14:53Z,10.0.0.1,auth_ok\n",
        encoding="utf-8",
    )

    settings = get_settings()
    settings.evidence_staging_path = str(staging_dir)

    tool = LogCsvParserTool()
    params = LogCsvParserParameters(
        evidence_id=evidence_id,
        format_preset="csv",
    )
    context = ToolExecutionContext(case_id=uuid.uuid4(), evidence_id=evidence_id)
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["source_id"] == evidence_id
    assert result.observations[0]["normalized_content"]["ip"] == "10.0.0.1"


# --- Auto-Detection Tests ---


@pytest.mark.asyncio
async def test_auto_detection_json_lines() -> None:
    """Verify format_preset='auto' correctly detects JSON Lines."""
    tool = LogCsvParserTool()
    ndjson = (
        '{"@timestamp": "2026-11-24T08:14:53Z", "user": "alice"}\n'
        '{"@timestamp": "2026-11-24T08:15:00Z", "user": "bob"}\n'
    )
    params = LogCsvParserParameters(content=ndjson, format_preset="auto")
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.metadata["format_preset"] == "json_lines"
    assert len(result.observations) == 2


@pytest.mark.asyncio
async def test_auto_detection_apache() -> None:
    """Verify format_preset='auto' correctly detects Apache Combined."""
    tool = LogCsvParserTool()
    apache = (
        '192.168.1.10 - - [24/Nov/2026:08:14:53 +0000] "GET /index.html HTTP/1.1" 200 450\n'
        '192.168.1.11 - - [24/Nov/2026:08:14:54 +0000] "GET /style.css HTTP/1.1" 200 120\n'
    )
    params = LogCsvParserParameters(content=apache, format_preset="auto")
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.metadata["format_preset"] == "apache_combined"
    assert len(result.observations) == 2


@pytest.mark.asyncio
async def test_auto_detection_syslog() -> None:
    """Verify format_preset='auto' correctly detects Syslog."""
    tool = LogCsvParserTool()
    syslog = (
        "Nov 24 08:14:53 srv1 kernel: [    0.000000] Initializing cgroup subsys cpuset\n"
        "Nov 24 08:14:54 srv1 systemd[1]: Started Network Service.\n"
    )
    params = LogCsvParserParameters(content=syslog, format_preset="auto")
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.metadata["format_preset"] == "syslog"
    assert len(result.observations) == 2


# --- ToolRunner Integration & Persistence Tests ---


@pytest.mark.asyncio
async def test_tool_runner_integration_nominal(db_session: Session, test_case: Case) -> None:
    """Verify ToolRunner persists ToolExecution and Observation entities."""
    registry = ToolRegistry()
    tool = LogCsvParserTool()
    registry.register(tool)

    runner = ToolRunner(db=db_session, registry=registry)
    context = ToolExecutionContext(
        case_id=test_case.id,
        agent_role="Executor",
    )

    csv_data = (
        "timestamp,ip,action,status\n"
        "2026-11-24T08:14:53Z,10.0.0.1,login,200\n"
        "2026-11-24T08:15:00Z,10.0.0.2,logout,200\n"
    )

    result = await runner.execute_tool(
        tool_name="parse_text_logs",
        parameters={
            "content": csv_data,
            "format_preset": "csv",
        },
        context=context,
    )

    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.result_sha256 is not None
    assert result.duration_ms > 0
    assert len(result.observations) == 2

    # Verify ToolExecution persisted in DB
    executions = db_session.query(ToolExecution).filter_by(case_id=test_case.id).all()
    assert len(executions) == 1
    exec_row = executions[0]
    assert exec_row.tool_name == "parse_text_logs"
    assert exec_row.status == ToolExecutionStatus.SUCCESS
    assert exec_row.result_sha256 == result.result_sha256

    # Verify Observation entities persisted in DB
    observations = db_session.query(Observation).filter_by(case_id=test_case.id).all()
    assert len(observations) == 2
    assert observations[0].timestamp_utc is not None
    assert observations[0].timestamp_utc.year == 2026
    assert observations[0].timestamp_utc.month == 11
    assert observations[0].timestamp_utc.day == 24
    assert observations[0].timestamp_utc.hour == 8
    assert observations[0].timestamp_utc.minute == 14
    assert observations[0].timestamp_utc.second == 53
    assert observations[0].source_location == "line:2"
    assert observations[0].normalized_content["ip"] == "10.0.0.1"
    assert observations[1].source_location == "line:3"
    assert observations[1].normalized_content["action"] == "logout"


@pytest.mark.asyncio
async def test_tool_runner_nonexistent_evidence_no_orphan(
    db_session: Session,
    test_case: Case,
    tmp_path: Path,
) -> None:
    """Verify tool with missing evidence raises exception with no orphan ToolExecution."""
    settings = get_settings()
    settings.evidence_staging_path = str(tmp_path / "staging")

    registry = ToolRegistry()
    registry.register(LogCsvParserTool())
    runner = ToolRunner(db=db_session, registry=registry)

    missing_id = uuid.uuid4()
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")

    with pytest.raises((ValidationException, NotFoundException)):
        await runner.execute_tool(
            tool_name="parse_text_logs",
            parameters={"evidence_id": str(missing_id)},
            context=context,
        )

    # Confirm no orphan ToolExecution in DB
    executions = db_session.query(ToolExecution).filter_by(case_id=test_case.id).all()
    assert len(executions) == 0


def test_default_registry_contains_log_parser() -> None:
    """Verify default_registry includes LogCsvParserTool automatically."""
    assert default_registry.has("parse_text_logs")
    tool = default_registry.get("parse_text_logs")
    assert isinstance(tool, LogCsvParserTool)
    assert tool.name == "parse_text_logs"
    assert tool.version == "1.0.0"
    assert tool.timeout_seconds == 60


def test_parse_timestamp_booleans_and_small_numbers() -> None:
    """Verify booleans and small numeric values (status codes/IDs) return None."""
    assert parse_timestamp_to_utc(True) is None
    assert parse_timestamp_to_utc(False) is None
    assert parse_timestamp_to_utc(200) is None
    assert parse_timestamp_to_utc(404) is None
    assert parse_timestamp_to_utc(1) is None
    assert parse_timestamp_to_utc("200") is None
    assert parse_timestamp_to_utc("404") is None
    assert parse_timestamp_to_utc(0) is None


def test_locale_independent_month_parsing() -> None:
    """Verify English month names in Syslog and CLF parse correctly regardless of locale."""
    dt_syslog = parse_timestamp_to_utc("Aug 15 12:30:45")
    assert dt_syslog is not None
    assert dt_syslog.month == 8
    assert dt_syslog.day == 15
    assert dt_syslog.hour == 12

    dt_clf = parse_timestamp_to_utc("15/Aug/2026:14:30:45 +0200")
    assert dt_clf is not None
    assert dt_clf == datetime(2026, 8, 15, 12, 30, 45, tzinfo=UTC)


@pytest.mark.asyncio
async def test_json_lines_null_timestamp_fallback() -> None:
    """Verify JSON Lines with null candidate timestamp falls through to subsequent key."""
    tool = LogCsvParserTool()
    ndjson = '{"@timestamp": null, "time": "2026-11-24T08:14:53Z", "ip": "10.0.0.1"}\n'
    params = LogCsvParserParameters(content=ndjson, format_preset="json_lines")
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["timestamp_utc"] == datetime(2026, 11, 24, 8, 14, 53, tzinfo=UTC)


@pytest.mark.asyncio
async def test_generic_parser_with_datetime_and_space() -> None:
    """Verify generic parser extracts date and time separated by space without losing time."""
    tool = LogCsvParserTool()
    content = "2026-11-24 08:14:53 kernel: [0.000] disk error detected from 192.168.1.1\n"
    params = LogCsvParserParameters(content=content, format_preset="auto")
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["timestamp_utc"] == datetime(2026, 11, 24, 8, 14, 53, tzinfo=UTC)
    assert result.observations[0]["normalized_content"]["ip"] == "192.168.1.1"


@pytest.mark.asyncio
async def test_utf8_bom_handling() -> None:
    """Verify UTF-8 BOM is stripped and headers/content parse cleanly."""
    tool = LogCsvParserTool()
    bom_content = "\ufefftimestamp,action\n2026-11-24T08:14:53Z,login\n"
    params = LogCsvParserParameters(content=bom_content, format_preset="csv")
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert "timestamp" in result.observations[0]["normalized_content"]
    assert result.observations[0]["normalized_content"]["action"] == "login"


@pytest.mark.asyncio
async def test_syslog_facility_and_severity_decoding() -> None:
    """Verify Syslog facility and severity are correctly computed from PRI (RFC 5424 and 3164)."""
    tool = LogCsvParserTool()
    # PRI 34 = facility 4 (auth), severity 2 (crit)
    content = (
        "<34>1 2026-11-24T08:14:53Z host app 123 ID1 - message 1\n"
        "<34>Nov 24 08:14:53 host app[123]: message 2\n"
    )
    params = LogCsvParserParameters(content=content, format_preset="syslog")
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 2
    assert result.observations[0]["normalized_content"]["pri"] == 34
    assert result.observations[0]["normalized_content"]["facility"] == 4
    assert result.observations[0]["normalized_content"]["severity"] == 2

    assert result.observations[1]["normalized_content"]["pri"] == 34
    assert result.observations[1]["normalized_content"]["facility"] == 4
    assert result.observations[1]["normalized_content"]["severity"] == 2


@pytest.mark.asyncio
async def test_key_value_unescaped_quotes() -> None:
    """Verify Key-Value parser properly unescapes escaped quotes."""
    tool = LogCsvParserTool()
    content = 'date=2026-11-24 time=08:14:53 msg="Access \\"blocked\\" by rule" action=deny\n'
    params = LogCsvParserParameters(content=content, format_preset="key_value")
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["normalized_content"]["msg"] == 'Access "blocked" by rule'


@pytest.mark.asyncio
async def test_max_records_truncation_and_metadata_flag() -> None:
    """Verify max_records limits observations and sets truncated=True in metadata."""
    tool = LogCsvParserTool()
    lines = [f"2026-11-24T08:14:{i:02d}Z,item_{i}\n" for i in range(10)]
    content = "timestamp,action\n" + "".join(lines)
    params = LogCsvParserParameters(content=content, format_preset="csv", max_records=3)
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 3
    assert result.metadata["parsed_records_count"] == 3
    assert result.metadata["truncated"] is True


@pytest.mark.asyncio
async def test_raw_output_contract_structure() -> None:
    """Verify raw_output adheres strictly to expected contract structure."""
    tool = LogCsvParserTool()
    content = "timestamp,ip,action\n2026-11-24T08:14:53Z,10.0.0.1,auth\n"
    params = LogCsvParserParameters(content=content, format_preset="csv")
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.raw_output["records_count"] == 1
    assert result.raw_output["total_lines"] == 2
    assert result.raw_output["errors_count"] == 0
    assert result.raw_output["format_preset"] == "csv"
    assert len(result.raw_output["records"]) == 1

    rec = result.raw_output["records"][0]
    assert rec["timestamp_utc"] == "2026-11-24T08:14:53+00:00"
    assert "raw" in rec
    assert "parsed_fields" in rec
    assert rec["parsed_fields"]["ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_custom_timestamp_field_and_format() -> None:
    """Verify custom timestamp_field and timestamp_format parameters."""
    tool = LogCsvParserTool()
    content = "custom_date;ip;action\n24/11/2026 08:14:53;10.0.0.5;login\n"
    params = LogCsvParserParameters(
        content=content,
        format_preset="csv",
        delimiter=";",
        timestamp_field="custom_date",
        timestamp_format="%d/%m/%Y %H:%M:%S",
    )
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["timestamp_utc"] == datetime(2026, 11, 24, 8, 14, 53, tzinfo=UTC)


@pytest.mark.asyncio
async def test_tsv_format_preset() -> None:
    """Verify TSV format preset parsing tab-separated values."""
    tool = LogCsvParserTool()
    content = "timestamp\tip\tstatus\n2026-11-24T08:14:53Z\t10.0.0.1\t200\n"
    params = LogCsvParserParameters(content=content, format_preset="tsv")
    context = ToolExecutionContext(case_id=uuid.uuid4())
    result = await tool.execute(params, context)

    assert result.status == ToolExecutionStatus.SUCCESS
    assert len(result.observations) == 1
    assert result.observations[0]["normalized_content"]["ip"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_tool_runner_evidence_id_persistence(
    db_session: Session,
    test_case: Case,
    test_evidence: Evidence,
) -> None:
    """Verify ToolRunner execution links Observation entities to evidence_id."""
    registry = ToolRegistry()
    registry.register(LogCsvParserTool())
    runner = ToolRunner(db=db_session, registry=registry)

    context = ToolExecutionContext(
        case_id=test_case.id,
        evidence_id=test_evidence.id,
        agent_role="Executor",
    )
    csv_data = "timestamp,action\n2026-11-24T08:14:53Z,import\n"

    result = await runner.execute_tool(
        tool_name="parse_text_logs",
        parameters={"content": csv_data, "format_preset": "csv"},
        context=context,
    )

    assert result.status == ToolExecutionStatus.SUCCESS
    observations = db_session.query(Observation).filter_by(case_id=test_case.id).all()
    assert len(observations) == 1
    assert observations[0].source_id == test_evidence.id
