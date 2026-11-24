"""IRYX Forensic Gateway ORM Models and Enums."""

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from iryx.analytics.models import Observation
from iryx.db.base import Base

if TYPE_CHECKING:
    from iryx.cases.models import Case


class ToolExecutionStatus(StrEnum):
    """Execution status lifecycle states for forensic tools."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ToolExecution(Base):
    """Auditable trace of every tool invocation performed via the Forensic Gateway."""

    __tablename__ = "tool_executions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tool_version: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_role: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        server_default=text("'{}'"),
        nullable=False,
    )
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    status: Mapped[ToolExecutionStatus] = mapped_column(
        String(32),
        default=ToolExecutionStatus.SUCCESS,
        server_default=text("'success'"),
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'error', 'timeout')",
            name="ck_tool_executions_status_check",
        ),
        CheckConstraint(
            "duration_ms >= 0",
            name="ck_tool_executions_duration_ms_non_negative",
        ),
    )

    case: Mapped["Case"] = relationship(
        "Case",
        back_populates="tool_executions",
    )
    observations: Mapped[list["Observation"]] = relationship(
        "Observation",
        back_populates="tool_execution",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __init__(self, **kw: Any) -> None:
        if kw.get("id") is None:
            kw["id"] = uuid.uuid4()
        if kw.get("status") is None:
            kw["status"] = ToolExecutionStatus.SUCCESS
        super().__init__(**kw)

    def __repr__(self) -> str:
        return (
            f"<ToolExecution id={self.id!r} tool_name={self.tool_name!r} "
            f"status={self.status!r} duration_ms={self.duration_ms!r}>"
        )


# Re-export Observation
__all__ = ["Observation", "ToolExecution", "ToolExecutionStatus"]

# Import related models for configure_mappers
import iryx.cases.models  # noqa: F401, E402
