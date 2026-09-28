"""What the advisor persists: conversations, turns, messages, tool calls, and token usage.

Retention (ADR 0012, decided by the owner): conversations, their turns and messages go 30
days after the last turn, or at once when deleted; tool calls stay 90 days and survive a
conversation's deletion, because an audit trail its subject can erase is not one; usage
stays 13 months for cost history. Purged lazily — see `advisor/store.py`.

**No money column anywhere.** Cost is computed from token counts and a price table, because
a per-call cost is a fraction of a cent and a `NUMERIC(19,2)` column would round it to zero
— and a cap that sums zeros never trips (docs/ADVISOR.md#numbers).

**Small value sets are `CHECK` constraints, not Postgres enums.** A turn's status or a
message's role may gain a value as the loop matures, and adding a label to a Postgres enum
is a migration that cannot run inside a transaction on older servers. A `CHECK` is changed
in an ordinary one.

Column names follow the OpenTelemetry GenAI attributes where one exists, so an exporter could
be added later without a migration — nothing exports traces today:

| Column | OpenTelemetry attribute |
|---|---|
| `advisor_tool_calls.tool_name` | `gen_ai.tool.name` |
| `advisor_tool_calls.tool_call_id` | `gen_ai.tool.call.id` |
| `advisor_usage.model` | `gen_ai.response.model` |
| `advisor_usage.provider` | `gen_ai.provider.name` |
| `advisor_usage.request_id` | `gen_ai.response.id` |
| `advisor_usage.input_tokens` | `gen_ai.usage.input_tokens` |
| `advisor_usage.output_tokens` | `gen_ai.usage.output_tokens` |
| `advisor_usage.stop_reason` | `gen_ai.response.finish_reasons` |
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _check(
    column: str, values: tuple[str, ...], name: str, nullable: bool = False
) -> CheckConstraint:
    listed = ", ".join(f"'{v}'" for v in values)
    clause = f"{column} IN ({listed})"
    return CheckConstraint(f"{column} IS NULL OR {clause}" if nullable else clause, name=name)


VIEWS = ("mine", "household")
TURN_STATUSES = ("streaming", "complete", "cancelled", "failed", "refused")
GROUNDINGS = ("verified", "flagged", "none")
FEEDBACK = ("good", "flagged")
ROLES = ("user", "assistant", "context", "tool_results")


class AdvisorConversation(Base):
    __tablename__ = "advisor_conversations"
    __table_args__ = (_check("view", VIEWS, "ck_advisor_conversations_view"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    #: Each person sees only their own conversations. RESTRICT, like stakes: members are
    #: deactivated, never deleted.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    view: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The first question, truncated. Typed by the owner, and treated as untrusted anyway.
    title_text: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_turn_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    #: 30 days after the last turn. The purge deletes by this, and its index.
    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    turns: Mapped[list[AdvisorTurn]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="AdvisorTurn.seq"
    )


class AdvisorTurn(Base):
    __tablename__ = "advisor_turns"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_advisor_turns_seq"),
        _check("status", TURN_STATUSES, "ck_advisor_turns_status"),
        _check("grounding", GROUNDINGS, "ck_advisor_turns_grounding"),
        _check("feedback", FEEDBACK, "ck_advisor_turns_feedback", nullable=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advisor_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="streaming")
    grounding: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    model: Mapped[str | None] = mapped_column(String(64))
    #: SHA-256 of the system prompt file, so an answer can be tied to the prompt it used.
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(32))
    #: The owner's verdict, for the monthly review. Never sent anywhere.
    feedback: Mapped[str | None] = mapped_column(String(16))
    feedback_note_text: Mapped[str | None] = mapped_column(String(500))
    feedback_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))

    conversation: Mapped[AdvisorConversation] = relationship(back_populates="turns")
    messages: Mapped[list[AdvisorMessage]] = relationship(
        back_populates="turn", cascade="all, delete-orphan", order_by="AdvisorMessage.seq"
    )


class AdvisorMessage(Base):
    """Content blocks exactly as sent or received, so history replays byte for byte.

    Prompt caching depends on it — any byte that moves invalidates the cache after it — and
    thinking blocks must be passed back unchanged.
    """

    __tablename__ = "advisor_messages"
    __table_args__ = (
        UniqueConstraint("turn_id", "seq", name="uq_advisor_messages_seq"),
        _check("role", ROLES, "ck_advisor_messages_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    turn_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("advisor_turns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    turn: Mapped[AdvisorTurn] = relationship(back_populates="messages")


class AdvisorToolCall(Base):
    """Every tool call, with its validated arguments — never its result.

    Survives the conversation's deletion (`SET NULL`) and is purged on its own 90-day clock.
    """

    __tablename__ = "advisor_tool_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advisor_conversations.id", ondelete="SET NULL"), index=True
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advisor_turns.id", ondelete="SET NULL"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(16), nullable=False)
    args: Mapped[Any] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    result_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    withheld_count: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The exception class when a call failed. Never its message.
    error: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class AdvisorUsage(Base):
    """Token counts for one model call. Cost is derived from these, never stored."""

    __tablename__ = "advisor_usage"

    id: Mapped[int] = mapped_column(primary_key=True)
    turn_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advisor_turns.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_write_5m_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_write_1h_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    stop_reason: Mapped[str | None] = mapped_column(String(32))
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
