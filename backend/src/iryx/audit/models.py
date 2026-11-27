"""IRYX Audit Event ORM model (append-only audit trail, Story 8.5)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from iryx.audit.triggers import install_audit_triggers
from iryx.core.integrity import LowercaseHex64Check
from iryx.db.base import Base


class AuditEvent(Base):
    """Append-only audit trail row; UPDATE/DELETE are rejected by a SQL trigger."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    details: Mapped[dict[str, object]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("length(action) > 0", name="ck_audit_events_action_check"),
        CheckConstraint(
            LowercaseHex64Check(payload_hash),
            name="ck_audit_events_payload_hash_hex_check",
        ),
        Index("ix_audit_events_case_id_created_at", "case_id", "created_at"),
    )

    def __repr__(self) -> str:
        """Return a representation that never exposes audit payload content."""
        return (
            f"<AuditEvent id={self.id!r} case_id={self.case_id!r} "
            f"action={self.action!r} created_at={self.created_at!r}>"
        )


def _install_audit_triggers_on_audit_events(target, connection, **kwargs) -> None:
    """Install the append-only SQL trigger after the ``audit_events`` table creation."""
    install_audit_triggers(connection)


event.listen(AuditEvent.__table__, "after_create", _install_audit_triggers_on_audit_events)
