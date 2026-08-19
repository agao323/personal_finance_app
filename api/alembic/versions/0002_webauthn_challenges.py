"""webauthn challenges

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-18

Ticket 034. The only schema change after the Wave 1 freeze: ceremonies need somewhere
to keep a challenge between issuing it and verifying the answer, and it has to be
server-side so a challenge can be spent exactly once.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webauthn_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("challenge_id", sa.String(length=64), nullable=False),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge_id"),
    )
    # Expired rows are swept opportunistically on each new ceremony rather than by a
    # cron: the table holds a handful of rows for one household, and a scheduled job
    # for that is more moving parts than the problem has.
    op.create_index(
        op.f("ix_webauthn_challenges_expires_at"),
        "webauthn_challenges",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_webauthn_challenges_expires_at"), table_name="webauthn_challenges")
    op.drop_table("webauthn_challenges")
