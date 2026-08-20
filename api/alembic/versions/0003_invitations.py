"""invitations

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-20

Ticket 043. A second household member cannot register a passkey any other way: the
bootstrap window is shut, and registering while the owner is signed in would attach
their authenticator to the owner's account.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Hashed, never the token itself. A readable invitation in the database is a
        # credential sitting in every backup.
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_invitations_user_id"), "invitations", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_invitations_user_id"), table_name="invitations")
    op.drop_table("invitations")
