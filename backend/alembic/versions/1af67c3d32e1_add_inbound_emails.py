"""add inbound emails

Revision ID: 1af67c3d32e1
Revises: d5ac83a6789e
Create Date: 2026-10-04 22:54:28.365935
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1af67c3d32e1"
down_revision: str | None = "d5ac83a6789e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = "receipts_inbound_email_id_fkey"  # Postgres's default name for this key


def upgrade() -> None:
    op.create_table(
        "inbound_emails",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("from_email", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("mailbox_hash", sa.String(length=255), nullable=True),
        sa.Column("is_receipt", sa.Boolean(), nullable=False),
        sa.Column("classification_reason", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )
    op.add_column(
        "receipts",
        sa.Column(
            "source",
            sa.Enum("upload", "email", name="receiptsource", native_enum=False, length=30),
            server_default="upload",
            nullable=False,
        ),
    )
    op.add_column("receipts", sa.Column("inbound_email_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_receipts_inbound_email_id"), "receipts", ["inbound_email_id"], unique=False
    )
    op.create_foreign_key(
        FK_NAME, "receipts", "inbound_emails", ["inbound_email_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint(FK_NAME, "receipts", type_="foreignkey")
    op.drop_index(op.f("ix_receipts_inbound_email_id"), table_name="receipts")
    op.drop_column("receipts", "inbound_email_id")
    op.drop_column("receipts", "source")
    op.drop_table("inbound_emails")
