"""add categories and receipt flags

Revision ID: d5ac83a6789e
Revises: 7953d14180a9
Create Date: 2026-10-04 21:40:39.444605
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5ac83a6789e"
down_revision: str | None = "7953d14180a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "receipt_flags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "extraction",
                "validation",
                "duplicate",
                "anomaly",
                name="flagkind",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("related_receipt_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["related_receipt_id"], ["receipts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_receipt_flags_receipt_id"), "receipt_flags", ["receipt_id"], unique=False
    )
    op.add_column("receipts", sa.Column("vendor_key", sa.String(length=255), nullable=True))
    op.add_column(
        "receipts",
        sa.Column(
            "category",
            sa.Enum(
                "groceries",
                "dining",
                "transportation",
                "travel",
                "shopping",
                "utilities",
                "health",
                "entertainment",
                "subscriptions",
                "education",
                "office",
                "other",
                name="category",
                native_enum=False,
                length=30,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "receipts",
        sa.Column(
            "category_source",
            sa.Enum(
                "llm", "vendor_history", "user", name="categorysource", native_enum=False, length=30
            ),
            nullable=True,
        ),
    )
    op.add_column("receipts", sa.Column("category_reason", sa.Text(), nullable=True))
    op.alter_column(
        "receipts",
        "status",
        existing_type=sa.VARCHAR(length=20),
        type_=sa.Enum("extracted", "failed", name="receiptstatus", native_enum=False, length=30),
        existing_nullable=False,
    )
    op.create_index(op.f("ix_receipts_category"), "receipts", ["category"], unique=False)
    op.create_index(op.f("ix_receipts_vendor_key"), "receipts", ["vendor_key"], unique=False)

    # Move existing validation issues into the new flags table before dropping the column.
    op.execute(
        """
        INSERT INTO receipt_flags (receipt_id, kind, code, message, created_at)
        SELECT r.id, 'validation', issue->>'code', issue->>'message', r.created_at
        FROM receipts r, jsonb_array_elements(r.validation_issues) AS issue
        """
    )
    op.execute(
        """
        INSERT INTO receipt_flags (receipt_id, kind, code, message, created_at)
        SELECT id, 'extraction', 'extraction_failed',
               'The receipt couldn''t be read automatically.', created_at
        FROM receipts WHERE status = 'failed'
        """
    )
    # Note: vendor_key isn't backfilled for older receipts; it's computed in Python on upload.
    op.drop_column("receipts", "needs_review")
    op.drop_column("receipts", "validation_issues")


def downgrade() -> None:
    op.add_column(
        "receipts",
        sa.Column(
            "validation_issues",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "receipts",
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Copy flags back into the old columns.
    op.execute(
        """
        UPDATE receipts r SET
          validation_issues = COALESCE((
            SELECT jsonb_agg(jsonb_build_object('code', f.code, 'message', f.message) ORDER BY f.id)
            FROM receipt_flags f WHERE f.receipt_id = r.id AND f.kind = 'validation'
          ), '[]'::jsonb),
          needs_review = EXISTS (
            SELECT 1 FROM receipt_flags f WHERE f.receipt_id = r.id AND f.dismissed_at IS NULL
          )
        """
    )
    op.drop_index(op.f("ix_receipts_vendor_key"), table_name="receipts")
    op.drop_index(op.f("ix_receipts_category"), table_name="receipts")
    op.alter_column(
        "receipts",
        "status",
        existing_type=sa.Enum(
            "extracted", "failed", name="receiptstatus", native_enum=False, length=30
        ),
        type_=sa.VARCHAR(length=20),
        existing_nullable=False,
    )
    op.drop_column("receipts", "category_reason")
    op.drop_column("receipts", "category_source")
    op.drop_column("receipts", "category")
    op.drop_column("receipts", "vendor_key")
    op.drop_index(op.f("ix_receipt_flags_receipt_id"), table_name="receipt_flags")
    op.drop_table("receipt_flags")
