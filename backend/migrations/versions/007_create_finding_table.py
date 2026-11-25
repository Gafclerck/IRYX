"""create finding table

Revision ID: 007
Revises: 006
Create Date: 2026-11-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _get_array_server_default() -> sa.text:
    """Return appropriate server default depending on SQL dialect."""
    try:
        bind = op.get_bind()
        dialect_name = bind.dialect.name if bind is not None else None
    except Exception:
        dialect_name = None
    if dialect_name is None:
        try:
            dialect_name = op.get_context().dialect.name
        except Exception:
            dialect_name = "postgresql"
    return sa.text("'{}'") if dialect_name == "postgresql" else sa.text("'[]'")


def upgrade() -> None:
    # 1. Create table findings
    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column(
            "severity",
            sa.String(length=32),
            server_default=sa.text("'low'"),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.String(length=32),
            server_default=sa.text("'medium'"),
            nullable=False,
        ),
        sa.Column(
            "finding_type",
            sa.String(length=32),
            server_default=sa.text("'fact'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default=sa.text("'proposed'"),
            nullable=False,
        ),
        sa.Column(
            "observation_refs",
            sa.JSON().with_variant(postgresql.ARRAY(postgresql.UUID(as_uuid=True)), "postgresql"),
            server_default=_get_array_server_default(),
            nullable=False,
        ),
        sa.Column(
            "tool_execution_refs",
            sa.JSON().with_variant(postgresql.ARRAY(postgresql.UUID(as_uuid=True)), "postgresql"),
            server_default=_get_array_server_default(),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name=op.f("fk_findings_case_id_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_findings_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_findings")),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name=op.f("ck_findings_severity_check"),
        ),
        sa.CheckConstraint(
            "confidence IN ('low', 'medium', 'high')",
            name=op.f("ck_findings_confidence_check"),
        ),
        sa.CheckConstraint(
            "finding_type IN ('fact', 'inference', 'hypothesis')",
            name=op.f("ck_findings_finding_type_check"),
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'validated', 'rejected')",
            name=op.f("ck_findings_status_check"),
        ),
    )
    op.create_index(
        op.f("ix_findings_case_id"),
        "findings",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_findings_status"),
        "findings",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_findings_severity"),
        "findings",
        ["severity"],
        unique=False,
    )
    op.create_index(
        op.f("ix_findings_created_by"),
        "findings",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_findings_created_at"),
        "findings",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_findings_created_at"), table_name="findings")
    op.drop_index(op.f("ix_findings_created_by"), table_name="findings")
    op.drop_index(op.f("ix_findings_severity"), table_name="findings")
    op.drop_index(op.f("ix_findings_status"), table_name="findings")
    op.drop_index(op.f("ix_findings_case_id"), table_name="findings")
    op.drop_table("findings")
