"""create case table

Revision ID: 003
Revises: 002
Create Date: 2026-11-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="open", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_cases_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_cases_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cases")),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'review', 'closed')",
            name=op.f("ck_cases_status_check"),
        ),
    )
    op.create_index(
        op.f("ix_cases_organization_id"),
        "cases",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cases_created_by"),
        "cases",
        ["created_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_cases_status"),
        "cases",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_cases_status"), table_name="cases")
    op.drop_index(op.f("ix_cases_created_by"), table_name="cases")
    op.drop_index(op.f("ix_cases_organization_id"), table_name="cases")
    op.drop_table("cases")
