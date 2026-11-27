"""finalize audit_events schema and enforce append-only access (Story 8.5)

Revision ID: 010
Revises: 009
Create Date: 2026-11-26

"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeEngine

from iryx.audit.triggers import AUDIT_TRIGGER_STATEMENTS
from iryx.core.integrity import LowercaseHex64Check

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_type() -> TypeEngine:
    """Return the generic UUID type matching the ORM metadata on every dialect."""
    return sa.Uuid()


def _json_type() -> TypeEngine:
    """Return the JSONB on PostgreSQL and portable JSON elsewhere."""
    try:
        bind = op.get_bind()
        dialect_name = bind.dialect.name if bind is not None else None
    except Exception:
        dialect_name = None
    if dialect_name is None:
        try:
            dialect_name = op.get_context().dialect.name
        except Exception:
            dialect_name = "sqlite"
    return postgresql.JSONB() if dialect_name == "postgresql" else sa.JSON()


def upgrade() -> None:
    """Finalize audit_events shape and install the append-only trigger."""
    op.drop_table("audit_events")

    op.create_table(
        "audit_events",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("case_id", _uuid_type(), nullable=True),
        sa.Column("actor_id", _uuid_type(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", _uuid_type(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("details", _json_type(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name=op.f("fk_audit_events_case_id_cases"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("length(action) > 0", name=op.f("ck_audit_events_action_check")),
        sa.CheckConstraint(
            LowercaseHex64Check(sa.column("payload_hash")),
            name=op.f("ck_audit_events_payload_hash_hex_check"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_case_id"), "audit_events", ["case_id"], unique=False)
    op.create_index(op.f("ix_audit_events_actor_id"), "audit_events", ["actor_id"], unique=False)
    op.create_index(op.f("ix_audit_events_action"), "audit_events", ["action"], unique=False)
    op.create_index(op.f("ix_audit_events_target_id"), "audit_events", ["target_id"], unique=False)
    op.create_index(
        op.f("ix_audit_events_payload_hash"), "audit_events", ["payload_hash"], unique=False
    )
    op.create_index(
        op.f("ix_audit_events_case_id_created_at"),
        "audit_events",
        ["case_id", "created_at"],
        unique=False,
    )
    statements = AUDIT_TRIGGER_STATEMENTS.get(
        op.get_bind().dialect.name,
        AUDIT_TRIGGER_STATEMENTS["postgresql"],
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    """Restore the Story 8.3 audit_events shape."""
    op.drop_index(op.f("ix_audit_events_case_id_created_at"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_payload_hash"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_action"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_target_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_actor_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_case_id"), table_name="audit_events")
    op.drop_table("audit_events")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS prevent_audit_event_mutation()")

    op.create_table(
        "audit_events",
        sa.Column("id", _uuid_type(), nullable=False),
        sa.Column("case_id", _uuid_type(), nullable=False),
        sa.Column("actor_id", _uuid_type(), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", _json_type(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_audit_events_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name=op.f("fk_audit_events_case_id_cases"),
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("length(event_type) > 0", name=op.f("ck_audit_events_event_type_check")),
        sa.CheckConstraint(
            LowercaseHex64Check(sa.column("payload_sha256")),
            name=op.f("ck_audit_events_payload_sha256_hex_check"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_case_id"), "audit_events", ["case_id"], unique=False)
    op.create_index(op.f("ix_audit_events_actor_id"), "audit_events", ["actor_id"], unique=False)
    op.create_index(
        op.f("ix_audit_events_event_type"), "audit_events", ["event_type"], unique=False
    )
    op.create_index(
        op.f("ix_audit_events_payload_sha256"), "audit_events", ["payload_sha256"], unique=False
    )
    op.create_index(
        op.f("ix_audit_events_case_id_created_at"),
        "audit_events",
        ["case_id", "created_at"],
        unique=False,
    )
