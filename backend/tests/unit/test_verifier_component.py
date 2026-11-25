"""Unit tests for FindingVerifier deterministic formal verifier (Story 6.3, FR23, NFR-REL-01).

Demonstrates zero LLM usage, nominal verification, hallucination rejection,
multi-tenant cross-case isolation (Invariant 1), batch SQL queries, and DB persistence.
"""

import ast
import inspect
import uuid
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from iryx.analytics.models import (
    Finding,
    FindingConfidence,
    FindingSeverity,
    FindingStatus,
    FindingType,
    Observation,
)
from iryx.auth.models import Organization, User
from iryx.cases.models import Case
from iryx.core.exceptions import HallucinatedReferenceException, ValidationException
from iryx.db.base import Base
from iryx.gateway.models import ToolExecution, ToolExecutionStatus
from iryx.orchestrator.verifier import (
    FindingVerifier,
    VerificationStatus,
)


@pytest.fixture
def db_session() -> Session:
    """In-memory SQLite session with all models created."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def setup_test_data(db_session: Session) -> dict[str, Any]:
    """Create test organization, user, two cases, and baseline forensic records."""
    org = Organization(name="SOC Investigation Unit")
    db_session.add(org)
    db_session.flush()

    user = User(
        email="analyst@iryx.io",
        hashed_password="hashed_pw_argon2",
    )
    db_session.add(user)
    db_session.flush()

    case_1 = Case(
        title="Incident Case 1 - Target",
        organization_id=org.id,
        created_by=user.id,
    )
    case_2 = Case(
        title="Incident Case 2 - Foreign Tenant",
        organization_id=org.id,
        created_by=user.id,
    )
    db_session.add_all([case_1, case_2])
    db_session.flush()

    # Tool execution and observation for Case 1
    tool_exec_case1 = ToolExecution(
        case_id=case_1.id,
        tool_name="parse_evtx",
        tool_version="1.0.0",
        agent_role="executor",
        status=ToolExecutionStatus.SUCCESS,
        duration_ms=45,
    )
    db_session.add(tool_exec_case1)
    db_session.flush()

    obs_case1 = Observation(
        case_id=case_1.id,
        tool_name="parse_evtx",
        tool_execution_id=tool_exec_case1.id,
        normalized_content={"event_id": 4688, "process": "cmd.exe"},
    )
    db_session.add(obs_case1)
    db_session.flush()

    # Tool execution and observation for Case 2 (Foreign)
    tool_exec_case2 = ToolExecution(
        case_id=case_2.id,
        tool_name="parse_registry",
        tool_version="1.0.0",
        agent_role="executor",
        status=ToolExecutionStatus.SUCCESS,
        duration_ms=60,
    )
    db_session.add(tool_exec_case2)
    db_session.flush()

    obs_case2 = Observation(
        case_id=case_2.id,
        tool_name="parse_registry",
        tool_execution_id=tool_exec_case2.id,
        normalized_content={"key": "RunOnce", "data": "evil.exe"},
    )
    db_session.add(obs_case2)
    db_session.commit()

    return {
        "org": org,
        "user": user,
        "case_1": case_1,
        "case_2": case_2,
        "tool_exec_case1": tool_exec_case1,
        "obs_case1": obs_case1,
        "tool_exec_case2": tool_exec_case2,
        "obs_case2": obs_case2,
    }


# ============================================================================
# 1. Zero LLM Guarantee (NFR-REL-01)
# ============================================================================


def test_zero_llm_guarantee_ast_check() -> None:
    """Verify strictly by AST that FindingVerifier has NO LLM imports (NFR-REL-01)."""
    import iryx.orchestrator.verifier as verifier_module

    source_code = inspect.getsource(verifier_module)
    parsed_ast = ast.parse(source_code)

    forbidden_keywords = {
        "openai",
        "UnifiedLLMClient",
        "get_llm_client",
        "LLMRole",
        "LLMResponse",
        "ChatCompletion",
        "langchain",
    }

    imported_names = set()
    for node in ast.walk(parsed_ast):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_names.add(node.module)
            for alias in node.names:
                imported_names.add(alias.name)

    violations = forbidden_keywords.intersection(imported_names)
    assert not violations, f"Forbidden LLM dependency imported in verifier: {violations}"
    assert "UnifiedLLMClient" not in source_code
    assert "get_llm_client" not in source_code


def test_zero_llm_purely_deterministic_execution(
    setup_test_data: dict[str, Any], db_session: Session
) -> None:
    """Verify FindingVerifier executes purely with SQL and Python logic without LLMs."""
    data = setup_test_data
    case_1 = data["case_1"]
    obs = data["obs_case1"]
    tool = data["tool_exec_case1"]

    finding_data = {
        "title": "Exécution de processus suspecte",
        "severity": "high",
        "confidence": "high",
        "finding_type": "fact",
        "observation_refs": [str(obs.id)],
        "tool_execution_refs": [str(tool.id)],
    }

    verifier = FindingVerifier(db=db_session)
    result = verifier.verify_sync(findings=[finding_data], case_id=case_1.id)

    assert result.status == VerificationStatus.COMPLETED
    assert result.total_findings == 1
    assert result.verified_count == 1
    assert result.rejected_count == 0
    assert result.details[0].is_valid is True
    assert result.details[0].is_verified is True
    assert result.details[0].status == FindingStatus.PROPOSED


# ============================================================================
# 2. Nominal Case: Certified Findings
# ============================================================================


def test_nominal_finding_certified_and_status_remains_proposed(
    setup_test_data: dict[str, Any], db_session: Session
) -> None:
    """Verify a finding with valid refs belonging to the case is verified and remains proposed."""
    data = setup_test_data
    case_1 = data["case_1"]
    obs = data["obs_case1"]
    tool = data["tool_exec_case1"]

    finding = Finding(
        case_id=case_1.id,
        title="Activité suspecte confirmée",
        severity=FindingSeverity.HIGH,
        confidence=FindingConfidence.HIGH,
        finding_type=FindingType.FACT,
        status=FindingStatus.PROPOSED,
        observation_refs=[obs.id],
        tool_execution_refs=[tool.id],
    )
    db_session.add(finding)
    db_session.commit()

    verifier = FindingVerifier(db=db_session)
    result = verifier.verify_sync(findings=[finding], case_id=case_1.id)

    assert result.status == VerificationStatus.COMPLETED
    assert result.verified_count == 1
    assert result.rejected_count == 0

    detail = result.details[0]
    assert detail.is_valid is True
    assert detail.is_verified is True
    assert detail.status == FindingStatus.PROPOSED
    assert detail.valid_observation_refs == [obs.id]
    assert detail.valid_tool_execution_refs == [tool.id]
    assert detail.rejection_reason is None

    # Verify DB status is still PROPOSED for human gate H2
    db_session.refresh(finding)
    assert finding.status == FindingStatus.PROPOSED


# ============================================================================
# 3. Hallucination Detection: Inexistent References
# ============================================================================


def test_hallucinated_observation_ref_rejected(
    setup_test_data: dict[str, Any], db_session: Session
) -> None:
    """Verify a finding citing a non-existent observation UUID is rejected as hallucination."""
    data = setup_test_data
    case_1 = data["case_1"]
    tool = data["tool_exec_case1"]
    fake_obs_id = uuid.uuid4()

    finding = Finding(
        case_id=case_1.id,
        title="Constat halluciné (observation fictive)",
        severity=FindingSeverity.CRITICAL,
        confidence=FindingConfidence.HIGH,
        finding_type=FindingType.FACT,
        status=FindingStatus.PROPOSED,
        observation_refs=[fake_obs_id],
        tool_execution_refs=[tool.id],
    )
    db_session.add(finding)
    db_session.commit()

    verifier = FindingVerifier(db=db_session)
    result = verifier.verify_sync(findings=[finding], case_id=case_1.id)

    assert result.status == VerificationStatus.COMPLETED
    assert result.verified_count == 0
    assert result.rejected_count == 1

    detail = result.details[0]
    assert detail.is_valid is False
    assert detail.is_verified is False
    assert detail.status == FindingStatus.REJECTED
    assert detail.rejection_reason == "HALLUCINATED_REFERENCE_DETECTED"
    assert str(fake_obs_id) in detail.missing_observation_refs

    # Verify DB persistence updated status to rejected
    db_session.refresh(finding)
    assert finding.status == FindingStatus.REJECTED


def test_hallucinated_tool_execution_ref_rejected(
    setup_test_data: dict[str, Any], db_session: Session
) -> None:
    """Verify a finding citing a non-existent tool execution UUID is rejected as hallucination."""
    data = setup_test_data
    case_1 = data["case_1"]
    obs = data["obs_case1"]
    fake_tool_id = uuid.uuid4()

    finding = Finding(
        case_id=case_1.id,
        title="Constat halluciné (outil fictif)",
        severity=FindingSeverity.MEDIUM,
        confidence=FindingConfidence.MEDIUM,
        finding_type=FindingType.INFERENCE,
        status=FindingStatus.PROPOSED,
        observation_refs=[obs.id],
        tool_execution_refs=[fake_tool_id],
    )
    db_session.add(finding)
    db_session.commit()

    verifier = FindingVerifier(db=db_session)
    result = verifier.verify_sync(findings=[finding], case_id=case_1.id)

    assert result.status == VerificationStatus.COMPLETED
    assert result.rejected_count == 1
    assert result.details[0].is_valid is False
    assert result.details[0].rejection_reason == "HALLUCINATED_REFERENCE_DETECTED"
    assert str(fake_tool_id) in result.details[0].missing_tool_execution_refs

    db_session.refresh(finding)
    assert finding.status == FindingStatus.REJECTED


# ============================================================================
# 4. Multi-Tenant Cross-Case Isolation (Invariant 1)
# ============================================================================


def test_cross_case_foreign_observation_ref_rejected(
    setup_test_data: dict[str, Any], db_session: Session
) -> None:
    """Verify a finding citing an observation from another case is rejected (Invariant 1)."""
    data = setup_test_data
    case_1 = data["case_1"]
    tool_case1 = data["tool_exec_case1"]
    foreign_obs = data["obs_case2"]  # Belongs to Case 2

    finding = Finding(
        case_id=case_1.id,
        title="Constat avec fuite multi-tenant (observation tiers)",
        severity=FindingSeverity.HIGH,
        confidence=FindingConfidence.HIGH,
        finding_type=FindingType.FACT,
        status=FindingStatus.PROPOSED,
        observation_refs=[foreign_obs.id],
        tool_execution_refs=[tool_case1.id],
    )
    db_session.add(finding)
    db_session.commit()

    verifier = FindingVerifier(db=db_session)
    result = verifier.verify_sync(findings=[finding], case_id=case_1.id)

    assert result.rejected_count == 1
    detail = result.details[0]
    assert detail.is_valid is False
    assert detail.rejection_reason == "HALLUCINATED_REFERENCE_DETECTED"
    assert detail.foreign_observation_refs == [foreign_obs.id]
    assert detail.missing_observation_refs == []

    db_session.refresh(finding)
    assert finding.status == FindingStatus.REJECTED


def test_cross_case_foreign_tool_execution_ref_rejected(
    setup_test_data: dict[str, Any], db_session: Session
) -> None:
    """Verify a finding citing a tool execution from another case is rejected (Invariant 1)."""
    data = setup_test_data
    case_1 = data["case_1"]
    obs_case1 = data["obs_case1"]
    foreign_tool = data["tool_exec_case2"]  # Belongs to Case 2

    finding = Finding(
        case_id=case_1.id,
        title="Constat avec fuite multi-tenant (outil tiers)",
        severity=FindingSeverity.HIGH,
        confidence=FindingConfidence.HIGH,
        finding_type=FindingType.FACT,
        status=FindingStatus.PROPOSED,
        observation_refs=[obs_case1.id],
        tool_execution_refs=[foreign_tool.id],
    )
    db_session.add(finding)
    db_session.commit()

    verifier = FindingVerifier(db=db_session)
    result = verifier.verify_sync(findings=[finding], case_id=case_1.id)

    assert result.rejected_count == 1
    detail = result.details[0]
    assert detail.is_valid is False
    assert detail.rejection_reason == "HALLUCINATED_REFERENCE_DETECTED"
    assert detail.foreign_tool_execution_refs == [foreign_tool.id]

    db_session.refresh(finding)
    assert finding.status == FindingStatus.REJECTED


# ============================================================================
# 5. Missing Anchors and Malformed Identifiers
# ============================================================================


def test_empty_observation_refs_rejected(
    setup_test_data: dict[str, Any], db_session: Session
) -> None:
    """Verify a finding with empty observation_refs is rejected for lack of anchor."""
    data = setup_test_data
    case_1 = data["case_1"]
    tool = data["tool_exec_case1"]

    finding_data = {
        "title": "Constat sans observation",
        "severity": "low",
        "observation_refs": [],
        "tool_execution_refs": [str(tool.id)],
    }

    verifier = FindingVerifier(db=db_session)
    result = verifier.verify_sync(findings=[finding_data], case_id=case_1.id)

    assert result.rejected_count == 1
    assert result.details[0].is_valid is False
    assert result.details[0].rejection_reason == "HALLUCINATED_REFERENCE_DETECTED"


def test_empty_tool_execution_refs_rejected(
    setup_test_data: dict[str, Any], db_session: Session
) -> None:
    """Verify a finding with empty tool_execution_refs is rejected for lack of anchor."""
    data = setup_test_data
    case_1 = data["case_1"]
    obs = data["obs_case1"]

    finding_data = {
        "title": "Constat sans outil",
        "severity": "low",
        "observation_refs": [str(obs.id)],
        "tool_execution_refs": [],
    }

    verifier = FindingVerifier(db=db_session)
    result = verifier.verify_sync(findings=[finding_data], case_id=case_1.id)

    assert result.rejected_count == 1
    assert result.details[0].is_valid is False
    assert result.details[0].rejection_reason == "HALLUCINATED_REFERENCE_DETECTED"


def test_malformed_uuid_refs_handled_gracefully(
    setup_test_data: dict[str, Any], db_session: Session
) -> None:
    """Verify strings that cannot be parsed as UUID are handled without crashing."""
    data = setup_test_data
    case_1 = data["case_1"]
    tool = data["tool_exec_case1"]

    finding_data = {
        "title": "Constat avec UUID corrompu",
        "severity": "low",
        "observation_refs": ["invalid-uuid-string-1234"],
        "tool_execution_refs": [str(tool.id)],
    }

    verifier = FindingVerifier(db=db_session)
    result = verifier.verify_sync(findings=[finding_data], case_id=case_1.id)

    assert result.rejected_count == 1
    detail = result.details[0]
    assert detail.is_valid is False
    assert "invalid-uuid-string-1234" in detail.missing_observation_refs


# ============================================================================
# 6. Batch SQL Queries & Multiple Findings
# ============================================================================


def test_batch_verification_multiple_findings(
    setup_test_data: dict[str, Any], db_session: Session
) -> None:
    """Verify batch processing correctly identifies valid, hallucinated, and cross-case findings."""
    data = setup_test_data
    case_1 = data["case_1"]
    obs1 = data["obs_case1"]
    tool1 = data["tool_exec_case1"]
    obs2 = data["obs_case2"]  # Foreign
    fake_uuid = uuid.uuid4()

    f1 = {
        "title": "F1 - Valid",
        "observation_refs": [str(obs1.id)],
        "tool_execution_refs": [str(tool1.id)],
    }
    f2 = {
        "title": "F2 - Hallucinated Obs",
        "observation_refs": [str(fake_uuid)],
        "tool_execution_refs": [str(tool1.id)],
    }
    f3 = {
        "title": "F3 - Cross-Case Obs",
        "observation_refs": [str(obs2.id)],
        "tool_execution_refs": [str(tool1.id)],
    }

    verifier = FindingVerifier(db=db_session)
    result = verifier.verify_sync(findings=[f1, f2, f3], case_id=case_1.id)

    assert result.total_findings == 3
    assert result.verified_count == 1
    assert result.rejected_count == 2
    assert result.details[0].is_valid is True
    assert result.details[1].is_valid is False
    assert result.details[2].is_valid is False


# ============================================================================
# 7. Edge Cases: Empty Findings and Missing DB Session
# ============================================================================


def test_empty_findings_list_completes_with_zero_count() -> None:
    """Verify empty findings list returns completed status without errors."""
    verifier = FindingVerifier()
    result = verifier.verify_sync(findings=[], case_id=uuid.uuid4())

    assert result.status == VerificationStatus.COMPLETED
    assert result.total_findings == 0
    assert result.verified_count == 0
    assert result.rejected_count == 0
    assert result.errors == []


def test_missing_db_session_with_findings_fails() -> None:
    """Verify verification fails with status='failed' when DB session is missing."""
    verifier = FindingVerifier(db=None)
    finding_data = {
        "title": "Constat orphelin",
        "observation_refs": [str(uuid.uuid4())],
        "tool_execution_refs": [str(uuid.uuid4())],
    }

    result = verifier.verify_sync(findings=[finding_data], case_id=uuid.uuid4())

    assert result.status == VerificationStatus.FAILED
    assert len(result.errors) == 1
    assert "session de base de données" in result.errors[0]


# ============================================================================
# 8. Asynchronous API Support
# ============================================================================


@pytest.mark.asyncio
async def test_async_verify_method(setup_test_data: dict[str, Any], db_session: Session) -> None:
    """Verify the asynchronous verify() method behaves identically to verify_sync()."""
    data = setup_test_data
    case_1 = data["case_1"]
    obs = data["obs_case1"]
    tool = data["tool_exec_case1"]

    finding_data = {
        "title": "Constat asynchrone",
        "observation_refs": [str(obs.id)],
        "tool_execution_refs": [str(tool.id)],
    }

    verifier = FindingVerifier(db=db_session)
    result = await verifier.verify(findings=[finding_data], case_id=case_1.id)

    assert result.status == VerificationStatus.COMPLETED
    assert result.verified_count == 1
    assert result.details[0].is_valid is True


# ============================================================================
# 9. Exception Hierarchy (FR23)
# ============================================================================


def test_hallucinated_reference_exception_structure() -> None:
    """Verify HallucinatedReferenceException conforms to IRYX exception hierarchy."""
    exc = HallucinatedReferenceException()
    assert isinstance(exc, ValidationException)
    assert exc.code == "HALLUCINATED_REFERENCE_DETECTED"
    assert "Référence forensique inexistante" in exc.message
