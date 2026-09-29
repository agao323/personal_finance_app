"""the monthly review: a conversation kind, and the month it reviews

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-29

Plan 119. A conversation is a `chat` or a `review` of one month. Existing rows are chats. A
review names its month, a chat never does, and a person has at most one review of a month —
the partial unique index is what lets the offer disappear once it is taken.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "advisor_conversations",
        sa.Column("kind", sa.String(16), nullable=False, server_default="chat"),
    )
    op.add_column("advisor_conversations", sa.Column("review_month", sa.Date(), nullable=True))
    op.create_check_constraint(
        "ck_advisor_conversations_kind", "advisor_conversations", "kind IN ('chat', 'review')"
    )
    op.create_check_constraint(
        "ck_advisor_conversations_review_month",
        "advisor_conversations",
        "(kind = 'review') = (review_month IS NOT NULL)",
    )
    op.create_index(
        "uq_advisor_conversations_review",
        "advisor_conversations",
        ["user_id", "review_month"],
        unique=True,
        postgresql_where=sa.text("kind = 'review'"),
    )


def downgrade() -> None:
    """Drops the columns: every review becomes an ordinary conversation."""
    op.drop_index("uq_advisor_conversations_review", table_name="advisor_conversations")
    op.drop_constraint("ck_advisor_conversations_review_month", "advisor_conversations")
    op.drop_constraint("ck_advisor_conversations_kind", "advisor_conversations")
    op.drop_column("advisor_conversations", "review_month")
    op.drop_column("advisor_conversations", "kind")
