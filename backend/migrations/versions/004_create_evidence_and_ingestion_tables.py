"""create evidence and ingestion tables

Revision ID: 004
Revises: 003
Create Date: 2026-11-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("detected_type", sa.String(length=255), nullable=True),
        sa.Column("imported_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name=op.f("fk_evidences_case_id_cases"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["imported_by"],
            ["users.id"],
            name=op.f("fk_evidences_imported_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidences")),
        sa.CheckConstraint(
            "file_size >= 0",
            name=op.f("ck_evidences_file_size_non_negative"),
        ),
    )
    op.create_index(
        op.f("ix_evidences_case_id"),
        "evidences",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidences_imported_by"),
        "evidences",
        ["imported_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidences_sha256"),
        "evidences",
        ["sha256"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidences_created_at"),
        "evidences",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidences.id"],
            name=op.f("fk_ingestion_runs_evidence_id_evidences"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_runs")),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name=op.f("ck_ingestion_runs_status_check"),
        ),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name=op.f("ck_ingestion_runs_progress_range"),
        ),
    )
    op.create_index(
        op.f("ix_ingestion_runs_evidence_id"),
        "ingestion_runs",
        ["evidence_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ingestion_runs_status"),
        "ingestion_runs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ingestion_runs_status"), table_name="ingestion_runs")
    op.drop_index(op.f("ix_ingestion_runs_evidence_id"), table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_index(op.f("ix_evidences_created_at"), table_name="evidences")
    op.drop_index(op.f("ix_evidences_sha256"), table_name="evidences")
    op.drop_index(op.f("ix_evidences_imported_by"), table_name="evidences")
    op.drop_index(op.f("ix_evidences_case_id"), table_name="evidences")
    op.drop_table("evidences")
