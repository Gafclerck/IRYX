"""IRYX Analytics, Observation, and Finding ORM Models."""

import contextlib
import json
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator

from iryx.db.base import Base

if TYPE_CHECKING:
    from iryx.auth.models import User
    from iryx.cases.models import Case
    from iryx.evidence.models import Evidence
    from iryx.gateway.models import ToolExecution


class FindingSeverity(StrEnum):
    """Severity levels for technical findings."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingConfidence(StrEnum):
    """Confidence levels for technical findings."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FindingType(StrEnum):
    """Epistemological classifications for investigation findings."""

    FACT = "fact"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"


class FindingStatus(StrEnum):
    """Lifecycle statuses for technical findings."""

    PROPOSED = "proposed"
    VALIDATED = "validated"
    REJECTED = "rejected"


class UUIDList(TypeDecorator):
    """Platform-independent list of UUIDs.

    Resolves to postgresql.ARRAY(postgresql.UUID(as_uuid=True)) on PostgreSQL
    and sa.JSON on SQLite, serializing/deserializing list of UUID objects.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(PG_UUID(as_uuid=True)))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return [] if dialect.name == "sqlite" else []
        if isinstance(value, (str, uuid.UUID)) or not isinstance(value, (list, tuple, set)):
            value = [value]
        if dialect.name == "postgresql":
            return [v if isinstance(v, uuid.UUID) else uuid.UUID(str(v)) for v in value]
        # SQLite / JSON: serialize as list of strings
        return [str(v) if isinstance(v, uuid.UUID) else str(uuid.UUID(str(v))) for v in value]

    def process_result_value(self, value: Any, dialect: Any) -> list[uuid.UUID]:
        if value is None:
            return []
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                return []
        if isinstance(value, (list, tuple)):
            result = []
            for item in value:
                if isinstance(item, uuid.UUID):
                    result.append(item)
                elif item:
                    with contextlib.suppress(ValueError, TypeError, AttributeError):
                        result.append(uuid.UUID(str(item)))
            return result
        return []


class Observation(Base):
    """Observation entity representing normalized technical facts extracted from evidence."""

    __tablename__ = "observations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidences.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tool_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_executions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    normalized_content: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    timestamp_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    source_location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    case: Mapped["Case"] = relationship(
        "Case",
        back_populates="observations",
    )
    evidence: Mapped[Optional["Evidence"]] = relationship(
        "Evidence",
        back_populates="observations",
        foreign_keys=[source_id],
    )
    tool_execution: Mapped[Optional["ToolExecution"]] = relationship(
        "ToolExecution",
        back_populates="observations",
        foreign_keys=[tool_execution_id],
    )

    __table_args__ = (Index("ix_observations_case_id_timestamp_utc", "case_id", "timestamp_utc"),)

    def __init__(self, **kw: Any) -> None:
        if kw.get("id") is None:
            kw["id"] = uuid.uuid4()
        if kw.get("timestamp_utc") is not None:
            ts = kw["timestamp_utc"]
            if isinstance(ts, datetime):
                kw["timestamp_utc"] = (
                    ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
                )
        super().__init__(**kw)

    def __repr__(self) -> str:
        return (
            f"<Observation id={self.id!r} case_id={self.case_id!r} "
            f"tool_name={self.tool_name!r} source_location={self.source_location!r}>"
        )


class Finding(Base):
    """Finding entity representing technical conclusions, inferences or hypotheses."""

    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(
        String(32),
        default=FindingSeverity.LOW,
        server_default=text("'low'"),
        nullable=False,
        index=True,
    )
    confidence: Mapped[FindingConfidence] = mapped_column(
        String(32),
        default=FindingConfidence.MEDIUM,
        server_default=text("'medium'"),
        nullable=False,
    )
    finding_type: Mapped[FindingType] = mapped_column(
        String(32),
        default=FindingType.FACT,
        server_default=text("'fact'"),
        nullable=False,
    )
    status: Mapped[FindingStatus] = mapped_column(
        String(32),
        default=FindingStatus.PROPOSED,
        server_default=text("'proposed'"),
        nullable=False,
        index=True,
    )
    observation_refs: Mapped[list[uuid.UUID]] = mapped_column(
        MutableList.as_mutable(UUIDList),
        default=list,
        server_default=text("'{}'"),
        nullable=False,
    )
    tool_execution_refs: Mapped[list[uuid.UUID]] = mapped_column(
        MutableList.as_mutable(UUIDList),
        default=list,
        server_default=text("'{}'"),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_findings_severity_check",
        ),
        CheckConstraint(
            "confidence IN ('low', 'medium', 'high')",
            name="ck_findings_confidence_check",
        ),
        CheckConstraint(
            "finding_type IN ('fact', 'inference', 'hypothesis')",
            name="ck_findings_finding_type_check",
        ),
        CheckConstraint(
            "status IN ('proposed', 'validated', 'rejected')",
            name="ck_findings_status_check",
        ),
    )

    case: Mapped["Case"] = relationship(
        "Case",
        back_populates="findings",
    )
    creator: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by],
    )

    def __init__(self, **kw: Any) -> None:
        if kw.get("id") is None:
            kw["id"] = uuid.uuid4()
        if kw.get("severity") is None:
            kw["severity"] = FindingSeverity.LOW
        if kw.get("confidence") is None:
            kw["confidence"] = FindingConfidence.MEDIUM
        if kw.get("finding_type") is None:
            kw["finding_type"] = FindingType.FACT
        if kw.get("status") is None:
            kw["status"] = FindingStatus.PROPOSED
        if kw.get("observation_refs") is None:
            kw["observation_refs"] = []
        if kw.get("tool_execution_refs") is None:
            kw["tool_execution_refs"] = []
        super().__init__(**kw)

    def __repr__(self) -> str:
        return (
            f"<Finding id={self.id!r} case_id={self.case_id!r} "
            f"title={self.title!r} severity={self.severity!r} status={self.status!r}>"
        )


# Import related models for configure_mappers
import iryx.auth.models  # noqa: F401, E402
import iryx.cases.models  # noqa: F401, E402
import iryx.evidence.models  # noqa: F401, E402
import iryx.gateway.models  # noqa: F401, E402
