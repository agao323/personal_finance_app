"""Where a turn is written down: conversations, turns, messages, the audit trail, and usage.

**Each write is its own short transaction** — docs/ADVISOR.md, "Transactions: an exception
to ADR 0005, on purpose". A turn lasts up to two minutes; holding one connection that long
starves a small pool, and audit rows must survive a turn that fails or is cancelled — an
audit log that rolls back with the error it should have recorded is not one. So nothing
here takes a long-lived session: it takes a `Transaction`, a factory for one short unit of
work.

Production passes `fresh_transaction`. The ordinary routes (status, list, delete) and the tests
pass `nested_in(session)`: a savepoint in a session that already exists.

**Purge** runs at the start of every advisor request and as `make advisor-purge`: conversations
30 days after their last turn, tool calls after 90 days, usage after 13 months (ADR 0012).
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import Delete, delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.advisor import pricing
from app.advisor.model import Usage
from app.advisor.tools import ToolOutcome
from app.models.advisor import (
    AdvisorConversation,
    AdvisorMessage,
    AdvisorToolCall,
    AdvisorTurn,
    AdvisorUsage,
)
from app.schemas.advisor import AdvisorErrorCode, Grounding, TurnStatus

Transaction = Callable[[], AbstractContextManager[Session]]

CONVERSATION_TTL = dt.timedelta(days=30)
TOOL_CALL_TTL = dt.timedelta(days=90)
USAGE_TTL_MONTHS = 13
#: A turn still `streaming` this long after it started belongs to a process that died. The
#: wall-clock limit is two minutes; this leaves room for the slowest honest finish.
ABANDONED_AFTER = dt.timedelta(minutes=5)

_CALL_ID = re.compile(r"^c(\d+)$")


@contextmanager
def fresh_transaction() -> Iterator[Session]:
    """Production: a new session and one transaction, committed on success."""
    from app.db import get_sessionmaker

    with get_sessionmaker()() as session, session.begin():
        yield session


def nested_in(session: Session) -> Transaction:
    """A savepoint inside an existing session, released on success.

    For the ordinary advisor routes, which use the request's session as every other route
    does, and for tests, whose session is joined to an outer transaction rolled back per test.
    """

    @contextmanager
    def scope() -> Iterator[Session]:
        with session.begin_nested():
            yield session

    return scope


def month_start(on: dt.date) -> dt.date:
    return on.replace(day=1)


def next_month(on: dt.date) -> dt.date:
    start = month_start(on)
    return (
        start.replace(year=start.year + 1, month=1)
        if start.month == 12
        else start.replace(month=start.month + 1)
    )


def months_before(moment: dt.datetime, months: int) -> dt.datetime:
    """The same instant `months` calendar months earlier, the day clamped to the month's end."""
    index = moment.year * 12 + (moment.month - 1) - months
    year, month = divmod(index, 12)
    month += 1
    last_day = (next_month(dt.date(year, month, 1)) - dt.timedelta(days=1)).day
    return moment.replace(year=year, month=month, day=min(moment.day, last_day))


def _at_midnight(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(), tzinfo=dt.UTC)


@dataclass(frozen=True)
class StartedTurn:
    turn_id: uuid.UUID
    seq: int


@dataclass(frozen=True)
class StoredMessage:
    turn_id: uuid.UUID
    role: str
    content: Any


@dataclass(frozen=True)
class Purged:
    conversations: int
    tool_calls: int
    usage: int


class TurnInProgressError(Exception):
    """Another turn in this conversation is still streaming."""


class Store:
    def __init__(self, transaction: Transaction) -> None:
        self._tx = transaction

    # ── conversations and turns ───────────────────────────────────────────────

    def create_conversation(
        self, user_id: int, view: str, title: str, now: dt.datetime
    ) -> uuid.UUID:
        with self._tx() as session:
            conversation = AdvisorConversation(
                user_id=user_id,
                view=view,
                title_text=title[:120],
                expires_at=now + CONVERSATION_TTL,
            )
            session.add(conversation)
            session.flush()
            return conversation.id

    def start_turn(
        self,
        conversation_id: uuid.UUID,
        *,
        question: str,
        context: str,
        now: dt.datetime,
        model: str,
        prompt_version: str,
    ) -> StartedTurn:
        """Open a turn with its question and per-turn context, or refuse if one is open.

        The conversation row is locked for the check, so two questions sent at once cannot
        both start. A turn left `streaming` by a process that died is closed as failed.
        """
        with self._tx() as session:
            session.execute(
                select(AdvisorConversation.id)
                .where(AdvisorConversation.id == conversation_id)
                .with_for_update()
            )
            session.execute(
                update(AdvisorTurn)
                .where(
                    AdvisorTurn.conversation_id == conversation_id,
                    AdvisorTurn.status == TurnStatus.STREAMING,
                    AdvisorTurn.started_at < now - ABANDONED_AFTER,
                )
                .values(
                    status=TurnStatus.FAILED, error_code=AdvisorErrorCode.TIMEOUT, finished_at=now
                )
            )
            open_turn = session.execute(
                select(AdvisorTurn.id).where(
                    AdvisorTurn.conversation_id == conversation_id,
                    AdvisorTurn.status == TurnStatus.STREAMING,
                )
            ).first()
            if open_turn is not None:
                raise TurnInProgressError
            seq = (
                session.execute(
                    select(func.coalesce(func.max(AdvisorTurn.seq), 0)).where(
                        AdvisorTurn.conversation_id == conversation_id
                    )
                ).scalar_one()
                + 1
            )
            turn = AdvisorTurn(
                conversation_id=conversation_id,
                seq=seq,
                status=TurnStatus.STREAMING,
                grounding=Grounding.NONE,
                model=model,
                prompt_version=prompt_version,
                started_at=now,
            )
            session.add(turn)
            session.flush()
            session.add_all(
                [
                    AdvisorMessage(
                        turn_id=turn.id,
                        seq=1,
                        role="user",
                        content=[{"type": "text", "text": question}],
                    ),
                    AdvisorMessage(
                        turn_id=turn.id,
                        seq=2,
                        role="context",
                        content=[{"type": "text", "text": context}],
                    ),
                ]
            )
            session.execute(
                update(AdvisorConversation)
                .where(AdvisorConversation.id == conversation_id)
                .values(last_turn_at=now, expires_at=now + CONVERSATION_TTL)
            )
            return StartedTurn(turn.id, seq)

    def add_message(self, turn_id: uuid.UUID, role: str, content: Any) -> None:
        with self._tx() as session:
            seq = session.execute(
                select(func.coalesce(func.max(AdvisorMessage.seq), 0)).where(
                    AdvisorMessage.turn_id == turn_id
                )
            ).scalar_one()
            session.add(AdvisorMessage(turn_id=turn_id, seq=seq + 1, role=role, content=content))

    def finish_turn(
        self,
        turn_id: uuid.UUID,
        *,
        status: TurnStatus,
        now: dt.datetime,
        grounding: Grounding = Grounding.NONE,
        error: AdvisorErrorCode | None = None,
        model: str | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": status,
            "grounding": grounding,
            "error_code": error,
            "finished_at": now,
        }
        if model is not None:
            values["model"] = model
        with self._tx() as session:
            session.execute(update(AdvisorTurn).where(AdvisorTurn.id == turn_id).values(**values))

    def history(self, conversation_id: uuid.UUID, *, before_seq: int) -> list[StoredMessage]:
        """Every message of the conversation's **complete** turns before `before_seq`, in order.

        A cancelled or failed turn can end on a tool call with no result, which the provider
        rejects; and its half-answer is not something the next turn should build on. So only
        complete turns are replayed — each exactly as stored.
        """
        with self._tx() as session:
            rows = session.execute(
                select(AdvisorMessage.turn_id, AdvisorMessage.role, AdvisorMessage.content)
                .join(AdvisorTurn, AdvisorTurn.id == AdvisorMessage.turn_id)
                .where(
                    AdvisorTurn.conversation_id == conversation_id,
                    AdvisorTurn.status == TurnStatus.COMPLETE,
                    AdvisorTurn.seq < before_seq,
                )
                .order_by(AdvisorTurn.seq, AdvisorMessage.seq)
            ).all()
            return [StoredMessage(turn_id, role, content) for turn_id, role, content in rows]

    def calls_issued(self, conversation_id: uuid.UUID) -> int:
        """How many call ids (`c1`, `c2`, …) this conversation has used, so the next is new.

        Read from the audit trail, which records every call — including those of a
        cancelled turn whose results were never stored.
        """
        with self._tx() as session:
            ids = session.execute(
                select(AdvisorToolCall.tool_call_id).where(
                    AdvisorToolCall.conversation_id == conversation_id
                )
            ).scalars()
            numbers = [int(m.group(1)) for m in map(_CALL_ID.match, ids) if m]
            return max(numbers, default=0)

    # ── audit and usage ───────────────────────────────────────────────────────

    def record_tool_call(
        self, conversation_id: uuid.UUID, turn_id: uuid.UUID, outcome: ToolOutcome
    ) -> None:
        with self._tx() as session:
            session.add(
                AdvisorToolCall(
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    tool_name=outcome.tool,
                    tool_call_id=outcome.call_id,
                    args=outcome.args,
                    status=outcome.status,
                    latency_ms=outcome.latency_ms,
                    row_count=outcome.row_count,
                    result_bytes=len(outcome.content.encode()),
                    withheld_count=outcome.withheld_count,
                    error=outcome.error,
                )
            )

    def record_usage(
        self,
        turn_id: uuid.UUID,
        *,
        provider: str,
        model: str,
        request_id: str | None,
        usage: Usage,
        stop_reason: str | None,
        latency_ms: int,
    ) -> None:
        with self._tx() as session:
            session.add(
                AdvisorUsage(
                    turn_id=turn_id,
                    provider=provider,
                    model=model,
                    request_id=request_id,
                    input_tokens=usage.input_tokens,
                    cache_write_5m_tokens=usage.cache_write_5m_tokens,
                    cache_write_1h_tokens=usage.cache_write_1h_tokens,
                    cache_read_tokens=usage.cache_read_tokens,
                    output_tokens=usage.output_tokens,
                    stop_reason=stop_reason,
                    latency_ms=latency_ms,
                )
            )

    # ── spend ─────────────────────────────────────────────────────────────────

    def _spent(self, *conditions: Any) -> Decimal:
        with self._tx() as session:
            rows: Sequence[AdvisorUsage] = (
                session.execute(select(AdvisorUsage).where(*conditions)).scalars().all()
            )
            return sum(
                (
                    pricing.cost_cents(
                        _counts(row), row.model, row.created_at.date(), provider=row.provider
                    )
                    for row in rows
                ),
                Decimal(0),
            )

    def month_spent(self, today: dt.date) -> Decimal:
        """Household-wide, calendar month in UTC — the monthly cap's measure."""
        return self._spent(
            AdvisorUsage.created_at >= _at_midnight(month_start(today)),
            AdvisorUsage.created_at < _at_midnight(next_month(today)),
        )

    def conversation_spent(self, conversation_id: uuid.UUID) -> Decimal:
        turns = select(AdvisorTurn.id).where(AdvisorTurn.conversation_id == conversation_id)
        return self._spent(AdvisorUsage.turn_id.in_(turns))

    def turn_spent(self, turn_id: uuid.UUID) -> Decimal:
        return self._spent(AdvisorUsage.turn_id == turn_id)

    # ── retention ─────────────────────────────────────────────────────────────

    def purge(self, now: dt.datetime) -> Purged:
        with self._tx() as session:
            conversations = _deleted(
                session, delete(AdvisorConversation).where(AdvisorConversation.expires_at <= now)
            )
            tool_calls = _deleted(
                session,
                delete(AdvisorToolCall).where(AdvisorToolCall.created_at < now - TOOL_CALL_TTL),
            )
            usage = _deleted(
                session,
                delete(AdvisorUsage).where(
                    AdvisorUsage.created_at < months_before(now, USAGE_TTL_MONTHS)
                ),
            )
            return Purged(conversations, tool_calls, usage)


def _deleted(session: Session, statement: Delete) -> int:
    result = cast("CursorResult[Any]", session.execute(statement))
    return int(result.rowcount)


def _counts(row: AdvisorUsage) -> Usage:
    return Usage(
        input_tokens=row.input_tokens,
        cache_write_5m_tokens=row.cache_write_5m_tokens,
        cache_write_1h_tokens=row.cache_write_1h_tokens,
        cache_read_tokens=row.cache_read_tokens,
        output_tokens=row.output_tokens,
    )
