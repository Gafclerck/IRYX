"""Unit tests for Forensic Gateway contextual truncation (FR9, FR10, NFR-PERF-06)."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.analytics.models import Observation
from iryx.auth.models import Membership, MembershipRole, Organization, User
from iryx.cases.models import Case
from iryx.db.base import Base
from iryx.gateway.base import BaseTool, ToolExecutionContext, ToolExecutionResult
from iryx.gateway.models import ToolExecution
from iryx.gateway.registry import ToolRegistry
from iryx.gateway.runner import ToolRunner
from iryx.gateway.schemas import (
    AgentPayload,
    ObservationListResponse,
    ToolExecutionListResponse,
)
from iryx.gateway.truncation import (
    MAX_AGENT_OBSERVATIONS,
    MAX_SUMMARY_BYTES,
    MAX_SUMMARY_LINES,
    truncate_for_agent,
)


class DummyParams(BaseModel):
    dummy_input: str = "test"


class DummyTool(BaseTool):
    name: str = "dummy_tool"
    version: str = "1.0.0"
    description: str = "Tool for testing truncation"
    timeout_seconds: int = 10
    parameters_schema: type[BaseModel] = DummyParams

    def __init__(self, count: int = 100, item_size: int = 10) -> None:
        super().__init__()
        self.count = count
        self.item_size = item_size

    async def execute(
        self,
        params: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        obs = [
            {
                "timestamp_utc": "2026-11-24T12:00:00Z",
                "source_location": f"evidence.log:{i}",
                "tool_name": self.name,
                "normalized_content": {"index": i, "payload": "X" * self.item_size},
            }
            for i in range(self.count)
        ]
        return ToolExecutionResult(
            raw_output={"events_count": self.count, "records": obs},
            observations=obs,
        )


def test_truncation_nominal_1000_observations() -> None:
    """Verify nominal truncation when tool produces 1 000 observations.

    Expected:
    - observations capped at 50 (MAX_AGENT_OBSERVATIONS)
    - summary bounded <= 8 192 bytes and <= 200 lines
    - banner: [TRUNCATED: 950 éléments masqués. Consulter Observation pour la totalité]
    - is_truncated is True
    - truncated_count is 950
    """
    raw_obs = [
        {
            "timestamp_utc": "2026-11-24T12:00:00Z",
            "source_location": f"Security.evtx:{i}",
            "tool_name": "parse_evtx",
            "normalized_content": {"event_id": 4624, "index": i},
        }
        for i in range(1000)
    ]

    payload: AgentPayload = truncate_for_agent(observations=raw_obs)

    assert isinstance(payload, AgentPayload)
    assert len(payload.observations) == MAX_AGENT_OBSERVATIONS
    assert payload.is_truncated is True
    assert payload.truncated_count == 950
    assert (
        "[TRUNCATED: 950 éléments masqués. Consulter Observation pour la totalité]"
        in payload.summary
    )
    assert len(payload.summary.encode("utf-8")) <= MAX_SUMMARY_BYTES
    assert len(payload.summary.splitlines()) <= MAX_SUMMARY_LINES


def test_truncation_short_output_15_observations() -> None:
    """Verify that short outputs (<= 50 observations within limits) are not truncated.

    Expected:
    - 15 observations kept intact
    - is_truncated is False
    - truncated_count is 0
    - no [TRUNCATED] banner in summary
    """
    raw_obs = [
        {
            "timestamp_utc": "2026-11-24T12:00:00Z",
            "source_location": f"auth.log:{i}",
            "tool_name": "parse_text_logs",
            "normalized_content": {"line": i, "message": f"User login {i}"},
        }
        for i in range(15)
    ]

    payload: AgentPayload = truncate_for_agent(observations=raw_obs)

    assert isinstance(payload, AgentPayload)
    assert len(payload.observations) == 15
    assert payload.is_truncated is False
    assert payload.truncated_count == 0
    assert "[TRUNCATED" not in payload.summary
    assert len(payload.summary.encode("utf-8")) <= MAX_SUMMARY_BYTES
    assert len(payload.summary.splitlines()) <= MAX_SUMMARY_LINES


def test_truncation_strict_byte_overflow_30_large_observations() -> None:
    """Verify byte overflow truncation when 30 observations exceed 10 KB.

    Expected:
    - 30 observations preserved in payload.observations
    - summary text bounded strictly <= 8 192 bytes
    - summary contains [TRUNCATED] banner
    - is_truncated is True
    """
    large_obs = [
        {
            "timestamp_utc": "2026-11-24T12:00:00Z",
            "source_location": f"dump.raw:{i}",
            "tool_name": "analyze_memory",
            "normalized_content": {"index": i, "buffer": "A" * 600},
        }
        for i in range(30)
    ]

    payload: AgentPayload = truncate_for_agent(observations=large_obs)

    assert isinstance(payload, AgentPayload)
    assert len(payload.observations) == 30
    assert payload.is_truncated is True
    assert payload.truncated_count == 0
    assert (
        "[TRUNCATED: Résumé textuel tronqué. Consulter Observation pour la totalité]"
        in payload.summary
    )
    assert len(payload.summary.encode("utf-8")) <= MAX_SUMMARY_BYTES
    assert len(payload.summary.splitlines()) <= MAX_SUMMARY_LINES


def test_truncation_strict_line_overflow() -> None:
    """Verify summary line truncation when line count exceeds 200 lines."""
    lots_of_lines = "\n".join(f"Line {i}: test log entry" for i in range(300))

    payload: AgentPayload = truncate_for_agent(
        observations=[],
        summary=lots_of_lines,
    )

    assert payload.is_truncated is True
    assert "[TRUNCATED" in payload.summary
    assert len(payload.summary.splitlines()) <= MAX_SUMMARY_LINES
    assert len(payload.summary.encode("utf-8")) <= MAX_SUMMARY_BYTES


def test_tool_execution_result_to_agent_payload_method() -> None:
    """Verify ToolExecutionResult.to_agent_payload() projection and caching."""
    obs = [
        {
            "timestamp_utc": "2026-11-24T12:00:00Z",
            "source_location": f"event.evtx:{i}",
            "tool_name": "parse_evtx",
            "normalized_content": {"event_id": 1000 + i},
        }
        for i in range(80)
    ]

    result = ToolExecutionResult(
        raw_output={"events": obs},
        observations=obs,
    )

    assert result.agent_payload is None
    payload = result.to_agent_payload()

    assert isinstance(payload, AgentPayload)
    assert result.agent_payload is payload
    assert payload.is_truncated is True
    assert payload.truncated_count == 30
    assert len(payload.observations) == MAX_AGENT_OBSERVATIONS


def test_database_persistence_untruncated() -> None:
    """Verify that 100% of observations and raw data remain fully persisted in PostgreSQL/DB."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()

    try:
        user = User(
            id=uuid.uuid4(),
            email="forensic@soc.iryx",
            hashed_password="hash",
            is_active=True,
        )
        org = Organization(id=uuid.uuid4(), name="SOC IRYX")
        membership = Membership(
            organization_id=org.id,
            user_id=user.id,
            role=MembershipRole.INVESTIGATOR,
        )
        case = Case(
            id=uuid.uuid4(),
            organization_id=org.id,
            title="Investigation Troncature",
            created_by=user.id,
        )
        db.add_all([user, org, membership, case])
        db.commit()

        # Tool producing 120 observations
        tool = DummyTool(count=120, item_size=50)
        registry = ToolRegistry(enforce_whitelist=False)
        registry.register(tool)
        runner = ToolRunner(db=db, registry=registry)

        context = ToolExecutionContext(
            case_id=case.id,
            agent_role="Executor",
            user_id=user.id,
        )

        res = None
        import asyncio

        res = asyncio.run(runner.execute_tool("dummy_tool", DummyParams(), context))

        # Check in-memory result
        assert res.agent_payload is not None
        assert res.agent_payload.is_truncated is True
        assert len(res.agent_payload.observations) == 50
        assert res.agent_payload.truncated_count == 70

        # Check database persistence: ALL 120 observations must be saved in database!
        total_obs_in_db = db.scalar(
            select(func.count(Observation.id)).where(Observation.case_id == case.id)
        )
        assert total_obs_in_db == 120

        # Check ToolExecution record
        exec_record = db.scalar(select(ToolExecution).where(ToolExecution.case_id == case.id))
        assert exec_record is not None
        assert exec_record.result_sha256 == res.result_sha256
        assert len(exec_record.result_sha256) == 64

    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_truncation_with_orm_models() -> None:
    """Verify truncate_for_agent correctly formats Observation ORM instances."""
    case_id = uuid.uuid4()
    obs_models = [
        Observation(
            id=uuid.uuid4(),
            case_id=case_id,
            tool_name="parse_evtx",
            normalized_content={"event_id": 4624, "target_user": f"user_{i}"},
            timestamp_utc=datetime.now(UTC),
            source_location=f"C:\\Security.evtx:{i}",
        )
        for i in range(20)
    ]

    payload = truncate_for_agent(observations=obs_models)

    assert isinstance(payload, AgentPayload)
    assert len(payload.observations) == 20
    assert payload.is_truncated is False
    assert payload.truncated_count == 0
    assert "user_0" in payload.summary


def test_populate_total_items_validator() -> None:
    """Verify @model_validator populates total_items from total when missing."""
    exec_id = uuid.uuid4()
    case_id = uuid.uuid4()
    record = {
        "id": exec_id,
        "case_id": case_id,
        "tool_name": "hash_sha256",
        "tool_version": "1.0.0",
        "agent_role": "Executor",
        "parameters": {},
        "duration_ms": 10,
        "status": "success",
        "created_at": datetime.now(UTC),
    }

    # Dict without total_items
    resp = ToolExecutionListResponse.model_validate(
        {"items": [record], "total": 42, "limit": 10, "offset": 0, "has_more": True}
    )
    assert resp.total == 42
    assert resp.total_items == 42

    obs_id = uuid.uuid4()
    obs_record = {
        "id": obs_id,
        "case_id": case_id,
        "tool_name": "parse_evtx",
        "normalized_content": {},
        "created_at": datetime.now(UTC),
    }
    obs_resp = ObservationListResponse.model_validate(
        {"items": [obs_record], "total": 15, "limit": 10, "offset": 0, "has_more": True}
    )
    assert obs_resp.total == 15
    assert obs_resp.total_items == 15
