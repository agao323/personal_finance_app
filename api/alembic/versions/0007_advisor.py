"""the advisor: conversations, turns, messages, tool calls, usage

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-27

Ticket 095. Five tables, one migration, hand-written and reviewed like every other. The
first migration of the advisor waves; 108, 109, 112 and 113 follow it in that order.

Retention is ADR 0012's: transcripts 30 days after the last turn, tool calls 90 days and
surviving a conversation's deletion, usage 13 months. No money column anywhere — cost is
derived from token counts. Small value sets are CHECK constraints rather than Postgres
enums, so a new turn status is an ordinary migration. See `models/advisor.py`.
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _now() -> sa.Column[Any]:
    """`created_at`, defaulting to the insert time, as every other table has it."""
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def upgrade() -> None:
    op.create_table(
        "advisor_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("view", sa.String(length=16), nullable=False),
        sa.Column("title_text", sa.String(length=120), nullable=False),
        _now(),
        sa.Column("last_turn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("view IN ('mine', 'household')", name="ck_advisor_conversations_view"),
    )
    op.create_index(
        "ix_advisor_conversations_user_id", "advisor_conversations", ["user_id"], unique=False
    )
    op.create_index(
        "ix_advisor_conversations_expires_at", "advisor_conversations", ["expires_at"], unique=False
    )

    op.create_table(
        "advisor_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("grounding", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("feedback", sa.String(length=16), nullable=True),
        sa.Column("feedback_note_text", sa.String(length=500), nullable=True),
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["advisor_conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "seq", name="uq_advisor_turns_seq"),
        sa.CheckConstraint(
            "status IN ('streaming', 'complete', 'cancelled', 'failed', 'refused')",
            name="ck_advisor_turns_status",
        ),
        sa.CheckConstraint(
            "grounding IN ('verified', 'flagged', 'none')", name="ck_advisor_turns_grounding"
        ),
        sa.CheckConstraint(
            "feedback IS NULL OR feedback IN ('good', 'flagged')", name="ck_advisor_turns_feedback"
        ),
    )
    op.create_index(
        "ix_advisor_turns_conversation_id", "advisor_turns", ["conversation_id"], unique=False
    )

    op.create_table(
        "advisor_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        # JSON, not JSONB: JSONB reorders object keys, and a replayed tool call whose
        # arguments come back in a different order is a different prompt — the cache after
        # it is lost. JSON keeps the text as written. See models/advisor.py.
        sa.Column("content", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        _now(),
        sa.ForeignKeyConstraint(["turn_id"], ["advisor_turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id", "seq", name="uq_advisor_messages_seq"),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'context', 'tool_results')",
            name="ck_advisor_messages_role",
        ),
    )
    op.create_index("ix_advisor_messages_turn_id", "advisor_messages", ["turn_id"], unique=False)

    op.create_table(
        "advisor_tool_calls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("turn_id", sa.Uuid(), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("tool_call_id", sa.String(length=16), nullable=False),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("result_bytes", sa.Integer(), nullable=False),
        sa.Column("withheld_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(length=64), nullable=True),
        _now(),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["advisor_conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["turn_id"], ["advisor_turns.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("conversation_id", "turn_id", "created_at"):
        op.create_index(
            f"ix_advisor_tool_calls_{column}", "advisor_tool_calls", [column], unique=False
        )

    op.create_table(
        "advisor_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("turn_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_5m_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_write_1h_tokens", sa.Integer(), nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("stop_reason", sa.String(length=32), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        _now(),
        sa.ForeignKeyConstraint(["turn_id"], ["advisor_turns.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_advisor_usage_turn_id", "advisor_usage", ["turn_id"], unique=False)
    op.create_index("ix_advisor_usage_created_at", "advisor_usage", ["created_at"], unique=False)


def downgrade() -> None:
    """Drops all five tables. Every transcript, audit row and usage count is lost — which
    for this data is a smaller loss than it sounds: transcripts expire in 30 days anyway."""
    op.drop_table("advisor_usage")
    op.drop_table("advisor_tool_calls")
    op.drop_table("advisor_messages")
    op.drop_table("advisor_turns")
    op.drop_table("advisor_conversations")
