"""Add daily usage counters for per-account daily limits.

Revision ID: ebf3eb2aeced
Revises: 40b4bf7fffcf
Create Date: 2026-10-22 15:31:13.330884
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ebf3eb2aeced"
down_revision: str | None = "40b4bf7fffcf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_usage",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("receipts", "questions", name="usagekind", native_enum=False, length=30),
            nullable=False,
        ),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("daily_usage_user_id_fkey"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "day", "kind", name=op.f("daily_usage_pkey")),
    )


def downgrade() -> None:
    op.drop_table("daily_usage")
