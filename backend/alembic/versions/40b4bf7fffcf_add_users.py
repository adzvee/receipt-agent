"""add users

Revision ID: 40b4bf7fffcf
Revises: 1af67c3d32e1
Create Date: 2026-10-17 17:28:10.429829
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "40b4bf7fffcf"
down_revision: str | None = "1af67c3d32e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Owner for receipts that existed before accounts did. Its password hash ("!") can never
# match a password, so nobody can log in as it.
LEGACY_EMAIL = "legacy@localhost"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("inbound_token", sa.String(length=64), nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("llm_requests_used", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("users_pkey")),
        sa.UniqueConstraint("email", name=op.f("users_email_key")),
        sa.UniqueConstraint("inbound_token", name=op.f("users_inbound_token_key")),
    )

    # Add the owner columns as nullable, give any existing rows an owner, then require it.
    for table in ("receipts", "inbound_emails"):
        op.add_column(table, sa.Column("user_id", sa.Integer(), nullable=True))
    op.execute(
        f"""
        INSERT INTO users (email, password_hash, inbound_token)
        SELECT '{LEGACY_EMAIL}', '!', md5(random()::text)
        WHERE EXISTS (SELECT 1 FROM receipts) OR EXISTS (SELECT 1 FROM inbound_emails)
        """
    )
    for table in ("receipts", "inbound_emails"):
        op.execute(
            f"UPDATE {table} SET user_id = (SELECT id FROM users WHERE email = '{LEGACY_EMAIL}')"
        )
        op.alter_column(table, "user_id", nullable=False)
        op.create_index(op.f(f"ix_{table}_user_id"), table, ["user_id"])
        op.create_foreign_key(
            op.f(f"{table}_user_id_fkey"), table, "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    # Replaced by users.inbound_token.
    op.drop_column("inbound_emails", "mailbox_hash")


def downgrade() -> None:
    op.add_column("inbound_emails", sa.Column("mailbox_hash", sa.String(length=255), nullable=True))
    for table in ("receipts", "inbound_emails"):
        op.drop_constraint(op.f(f"{table}_user_id_fkey"), table, type_="foreignkey")
        op.drop_index(op.f(f"ix_{table}_user_id"), table_name=table)
        op.drop_column(table, "user_id")
    op.drop_table("users")
