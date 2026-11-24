"""Unit tests for ToolRunner: timeouts, SHA-256 calculation, and shell=False safety."""

import asyncio
import hashlib
import sys
import uuid
from collections.abc import Generator

import pytest
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.auth.models import Organization
from iryx.cases.models import Case
from iryx.core.exceptions import (
    PluginNotWhitelistedException,
    ToolExecutionFailedException,
    ToolExecutionTimeoutException,
    ToolNotFoundException,
    ValidationException,
)
from iryx.db.base import Base
from iryx.gateway.base import BaseTool, ToolExecutionContext, ToolExecutionResult
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.gateway.registry import ToolRegistry
from iryx.gateway.runner import ToolRunner, compute_sha256, run_command_safely


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
    org = Organization(name="CERT Runner")
    db_session.add(org)
    db_session.commit()

    case = Case(organization_id=org.id, title="Affaire Runner Test")
    db_session.add(case)
    db_session.commit()
    return case


# --- Test Tool Definitions ---


class SimpleInputSchema(BaseModel):
    data: str
    count: int = Field(default=1, ge=1)


class NominalTool(BaseTool):
    name = "hash_sha256"
    version = "1.0.0"
    description = "Nominal hashing test tool"
    timeout_seconds = 10
    parameters_schema = SimpleInputSchema

    async def execute(
        self,
        params: SimpleInputSchema,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        # Simulate quick work
        await asyncio.sleep(0.01)
        output = {"digest": hashlib.sha256(params.data.encode("utf-8")).hexdigest()}
        observations = [
            {
                "normalized_content": {"hash": output["digest"]},
                "source_location": "offset:0",
            }
        ]
        return ToolExecutionResult(
            raw_output=output,
            observations=observations,
            metadata={"processed_by": context.agent_role},
        )


class TimeoutTool(BaseTool):
    name = "parse_text_logs"
    version = "1.0.0"
    description = "Tool intentionally exceeding timeout"
    timeout_seconds = 1  # 1 second timeout
    parameters_schema = SimpleInputSchema

    async def execute(
        self,
        params: SimpleInputSchema,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        # Sleep for 5 seconds to guarantee timeout
        await asyncio.sleep(5)
        return ToolExecutionResult(raw_output={"done": True})


class FaultyTool(BaseTool):
    name = "parse_evtx"
    version = "1.0.0"
    description = "Tool intentionally raising an unexpected internal exception"
    timeout_seconds = 10
    parameters_schema = SimpleInputSchema

    async def execute(
        self,
        params: SimpleInputSchema,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        raise RuntimeError("Corruption fatale dans le parseur binaire")


# --- Unit Tests for ToolRunner ---


@pytest.mark.asyncio
async def test_nominal_tool_execution(db_session: Session, test_case: Case) -> None:
    """Verify nominal execution: status success, duration_ms > 0, SHA-256 computed, DB persisted."""
    registry = ToolRegistry()
    tool = NominalTool()
    registry.register(tool)

    runner = ToolRunner(db=db_session, registry=registry)
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")

    result = await runner.execute_tool(
        tool_name="hash_sha256",
        parameters={"data": "test payload", "count": 2},
        context=context,
    )

    # Verify result object
    assert result.status == ToolExecutionStatus.SUCCESS
    assert result.duration_ms > 0
    assert result.result_sha256 is not None
    assert len(result.result_sha256) == 64
    assert result.tool_execution_id is not None

    # Verify DB persistence of ToolExecution
    execution = db_session.get(ToolExecution, result.tool_execution_id)
    assert execution is not None
    assert execution.case_id == test_case.id
    assert execution.tool_name == "hash_sha256"
    assert execution.tool_version == "1.0.0"
    assert execution.agent_role == "Executor"
    assert execution.status == ToolExecutionStatus.SUCCESS
    assert execution.duration_ms > 0
    assert execution.result_sha256 == result.result_sha256
    assert execution.parameters == {"data": "test payload", "count": 2}
    assert execution.error_message is None

    # Verify Observation persistence
    assert len(execution.observations) == 1
    obs = execution.observations[0]
    assert obs.case_id == test_case.id
    assert obs.tool_name == "hash_sha256"
    assert obs.tool_execution_id == execution.id
    assert "hash" in obs.normalized_content


@pytest.mark.asyncio
async def test_tool_timeout_handling(db_session: Session, test_case: Case) -> None:
    """Verify timeout interruption: persists ToolExecution with status timeout and raises 504."""
    registry = ToolRegistry()
    tool = TimeoutTool()
    registry.register(tool)

    runner = ToolRunner(db=db_session, registry=registry)
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")

    with pytest.raises(ToolExecutionTimeoutException) as exc_info:
        await runner.execute_tool(
            tool_name="parse_text_logs",
            parameters={"data": "timeout test", "count": 1},
            context=context,
        )

    assert exc_info.value.status_code == 504

    # Verify ToolExecution record was saved in DB with TIMEOUT status
    executions = db_session.query(ToolExecution).filter_by(tool_name="parse_text_logs").all()
    assert len(executions) == 1
    exec_record = executions[0]
    assert exec_record.status == ToolExecutionStatus.TIMEOUT
    assert exec_record.result_sha256 is None
    assert exec_record.error_message is not None
    assert "délai" in exec_record.error_message.lower()


@pytest.mark.asyncio
async def test_unregistered_tool_handling(db_session: Session, test_case: Case) -> None:
    """Verify execution of unregistered tool raises ToolNotFoundException (404).

    Also verifies that no orphan record is persisted.
    """
    registry = ToolRegistry()
    runner = ToolRunner(db=db_session, registry=registry)
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")

    with pytest.raises(ToolNotFoundException) as exc_info:
        await runner.execute_tool(
            tool_name="unregistered_tool",
            parameters={"data": "abc"},
            context=context,
        )

    assert exc_info.value.status_code == 404

    # Verify no orphan ToolExecution was recorded
    count = db_session.query(ToolExecution).count()
    assert count == 0


@pytest.mark.asyncio
async def test_invalid_parameters_handling(db_session: Session, test_case: Case) -> None:
    """Verify invalid parameters raise ValidationException (422) before execution starts."""
    registry = ToolRegistry()
    registry.register(NominalTool())

    runner = ToolRunner(db=db_session, registry=registry)
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")

    # count must be ge=1, passing count=0 violates schema
    with pytest.raises(ValidationException) as exc_info:
        await runner.execute_tool(
            tool_name="hash_sha256",
            parameters={"data": "valid", "count": 0},
            context=context,
        )

    assert exc_info.value.status_code == 422

    # Verify no execution occurred or was recorded
    count = db_session.query(ToolExecution).count()
    assert count == 0


@pytest.mark.asyncio
async def test_tool_internal_error_handling(db_session: Session, test_case: Case) -> None:
    """Verify tool raising error persists error status and raises ToolExecutionFailedException."""
    registry = ToolRegistry()
    registry.register(FaultyTool())

    runner = ToolRunner(db=db_session, registry=registry)
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")

    with pytest.raises(ToolExecutionFailedException) as exc_info:
        await runner.execute_tool(
            tool_name="parse_evtx",
            parameters={"data": "trigger fault"},
            context=context,
        )

    assert exc_info.value.status_code == 500

    # Verify DB record has status ERROR
    executions = db_session.query(ToolExecution).filter_by(tool_name="parse_evtx").all()
    assert len(executions) == 1
    exec_record = executions[0]
    assert exec_record.status == ToolExecutionStatus.ERROR
    assert exec_record.result_sha256 is None
    assert "Corruption fatale" in (exec_record.error_message or "")


@pytest.mark.asyncio
async def test_subprocess_shell_false_safety() -> None:
    """Verify command execution is strictly shell=False and preserves argument literals."""
    # Test arguments with metacharacters (&&, ;, |)
    dangerous_arg = "alpha && beta; echo injected | cat"
    python_binary = sys.executable

    # Run Python printing sys.argv[1]
    code, stdout_data, stderr_data = await run_command_safely(
        [python_binary, "-c", "import sys; print(sys.argv[1])", dangerous_arg],
        timeout=10,
    )

    assert code == 0
    assert stdout_data.decode("utf-8").strip() == dangerous_arg

    # Rejection of string (must be list/tuple)
    with pytest.raises(ValidationException, match="must be provided as a list"):
        await run_command_safely(f"{python_binary} -c 'print(1)'")  # type: ignore

    # Rejection of empty list
    with pytest.raises(ValidationException, match="cannot be empty"):
        await run_command_safely([])


@pytest.mark.asyncio
async def test_subprocess_timeout() -> None:
    """Verify run_command_safely enforces timeouts."""
    python_binary = sys.executable

    with pytest.raises(ToolExecutionTimeoutException):
        await run_command_safely(
            [python_binary, "-c", "import time; time.sleep(5)"],
            timeout=0.5,
        )


def test_sha256_determinism() -> None:
    """Verify deterministic SHA-256 calculation for various data types."""
    # Dict
    hash1 = compute_sha256({"a": 1, "b": 2})
    hash2 = compute_sha256({"b": 2, "a": 1})
    assert hash1 == hash2

    # Bytes
    raw_bytes = b"evidence raw bytes"
    expected = hashlib.sha256(raw_bytes).hexdigest()
    assert compute_sha256(raw_bytes) == expected

    # String
    raw_str = "evidence string"
    assert compute_sha256(raw_str) == hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    # None
    assert compute_sha256(None) == hashlib.sha256(b"").hexdigest()

    # BaseModel
    class SampleModel(BaseModel):
        field: str

    model_hash = compute_sha256(SampleModel(field="value"))
    assert len(model_hash) == 64


def test_tool_execution_result_model_validator_output_alias() -> None:
    """Verify ToolExecutionResult maps output alias to raw_output via model_validator."""
    result = ToolExecutionResult(output={"key": "value"})
    assert result.raw_output == {"key": "value"}
    assert result.output == {"key": "value"}


@pytest.mark.asyncio
async def test_inner_tool_timeout_persists_timeout_status(
    db_session: Session, test_case: Case
) -> None:
    """Verify inner ToolExecutionTimeoutException from commands persists TIMEOUT status."""

    class InnerTimeoutTool(BaseTool):
        name = "hash_sha256"
        version = "1.0.0"
        description = "Tool raising inner ToolExecutionTimeoutException"
        timeout_seconds = 60
        parameters_schema = SimpleInputSchema

        async def execute(self, params: SimpleInputSchema, context: ToolExecutionContext):
            raise ToolExecutionTimeoutException("Inner command timed out")

    registry = ToolRegistry()
    registry.register(InnerTimeoutTool())
    runner = ToolRunner(db=db_session, registry=registry)
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")

    with pytest.raises(ToolExecutionTimeoutException):
        await runner.execute_tool(
            tool_name="hash_sha256",
            parameters={"data": "test"},
            context=context,
        )

    executions = db_session.query(ToolExecution).filter_by(tool_name="hash_sha256").all()
    assert len(executions) == 1
    assert executions[0].status == ToolExecutionStatus.TIMEOUT


@pytest.mark.asyncio
async def test_plugin_not_whitelisted_exception_not_converted_to_500(
    db_session: Session, test_case: Case
) -> None:
    """Verify PluginNotWhitelistedException is re-raised directly (403), not as 500."""

    class PluginRestrictedTool(BaseTool):
        name = "analyze_memory"
        version = "1.0.0"
        description = "Tool throwing PluginNotWhitelistedException"
        timeout_seconds = 10
        parameters_schema = SimpleInputSchema

        async def execute(self, params: SimpleInputSchema, context: ToolExecutionContext):
            raise PluginNotWhitelistedException("Unauthorized plugin")

    registry = ToolRegistry()
    registry.register(PluginRestrictedTool())
    runner = ToolRunner(db=db_session, registry=registry)
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")

    with pytest.raises(PluginNotWhitelistedException) as exc_info:
        await runner.execute_tool(
            tool_name="analyze_memory",
            parameters={"data": "test"},
            context=context,
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_observation_iso_timestamp_parsing(db_session: Session, test_case: Case) -> None:
    """Verify ISO-8601 string timestamp_utc in observations is parsed into datetime."""

    class IsoTimestampTool(BaseTool):
        name = "parse_text_logs"
        version = "1.0.0"
        description = "Tool returning ISO string timestamp"
        timeout_seconds = 10
        parameters_schema = SimpleInputSchema

        async def execute(self, params: SimpleInputSchema, context: ToolExecutionContext):
            return ToolExecutionResult(
                raw_output={"done": True},
                observations=[
                    {
                        "normalized_content": {"msg": "event"},
                        "timestamp_utc": "2026-11-24T12:00:00+00:00",
                        "source_location": "line 1",
                    }
                ],
            )

    registry = ToolRegistry()
    registry.register(IsoTimestampTool())
    runner = ToolRunner(db=db_session, registry=registry)
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")

    result = await runner.execute_tool(
        tool_name="parse_text_logs",
        parameters={"data": "test"},
        context=context,
    )
    execution = db_session.get(ToolExecution, result.tool_execution_id)
    assert execution is not None
    assert len(execution.observations) == 1
    obs = execution.observations[0]
    assert obs.timestamp_utc is not None
    assert obs.timestamp_utc.year == 2026
    assert obs.timestamp_utc.month == 11
    assert obs.timestamp_utc.day == 24


@pytest.mark.asyncio
async def test_params_dict_json_primitives(db_session: Session, test_case: Case) -> None:
    """Verify parameters containing UUID are serialized to clean JSON primitives."""

    class UuidParamSchema(BaseModel):
        target_id: uuid.UUID

    class UuidParamTool(BaseTool):
        name = "hash_sha256"
        version = "1.0.0"
        description = "Tool with UUID param"
        timeout_seconds = 10
        parameters_schema = UuidParamSchema

        async def execute(self, params: UuidParamSchema, context: ToolExecutionContext):
            return ToolExecutionResult(raw_output={"ok": True})

    registry = ToolRegistry()
    registry.register(UuidParamTool())
    runner = ToolRunner(db=db_session, registry=registry)
    context = ToolExecutionContext(case_id=test_case.id, agent_role="Executor")

    sample_uuid = uuid.uuid4()
    result = await runner.execute_tool(
        tool_name="hash_sha256",
        parameters={"target_id": sample_uuid},
        context=context,
    )
    execution = db_session.get(ToolExecution, result.tool_execution_id)
    assert execution is not None
    assert isinstance(execution.parameters["target_id"], str)
    assert execution.parameters["target_id"] == str(sample_uuid)


@pytest.mark.asyncio
async def test_subprocess_cancellation() -> None:
    """Verify run_command_safely cleans up and re-raises asyncio.CancelledError."""
    python_binary = sys.executable

    task = asyncio.create_task(
        run_command_safely(
            [python_binary, "-c", "import time; time.sleep(10)"],
            timeout=30,
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
