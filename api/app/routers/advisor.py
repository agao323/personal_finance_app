"""The advisor: conversations, streamed turns, feedback, and whether it is on.

Declared whole by ticket 081 and stubbed at 501; each route names the ticket that lands
it. The design is docs/ADVISOR.md, and the constraints it answers to are
docs/SECURITY.md#ai-agent.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from fastapi import APIRouter, Response, status
from fastapi.responses import StreamingResponse

from app.advisor.loop import configured, refusal
from app.advisor.pricing import display_cents
from app.advisor.store import Store, nested_in, next_month
from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.routers._stub import not_implemented
from app.schemas.advisor import (
    AdvisorErrorCode,
    AdvisorEvent,
    AdvisorProvider,
    AdvisorStatus,
    ConversationCreate,
    ConversationDetail,
    ConversationSummary,
    TurnCreate,
    TurnFeedback,
    TurnRead,
)
from app.schemas.common import ErrorResponse

router = APIRouter(
    prefix="/advisor",
    tags=["advisor"],
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)


class EventStreamResponse(StreamingResponse):
    """A streamed `text/event-stream` body.

    A named class rather than a bare `StreamingResponse` so the OpenAPI schema files the
    event model under the media type that actually crosses the wire, not under
    `application/json`, which a streamed route never sends.
    """

    media_type = "text/event-stream"


#: How a streamed route is described. `model` is what puts `AdvisorEvent` in the
#: generated types — the union is only ever sent as SSE, and without this the frontend
#: would have to hand-write it.
_EVENT_STREAM: dict[int | str, dict[str, Any]] = {
    200: {
        "model": AdvisorEvent,
        "description": "Server-sent events, one `AdvisorEvent` JSON object per `data:` line.",
    }
}


@router.get("/status", response_model=AdvisorStatus)
def get_status(session: DbSession, user: CurrentUser) -> AdvisorStatus:
    """Whether a question can be asked now and, if not, why; and this month's spend."""
    settings = get_settings()
    store = Store(nested_in(session))
    now = dt.datetime.now(dt.UTC)
    store.purge(now)
    today = now.date()
    spent = store.month_spent(today)
    cap = settings.advisor_monthly_cap_cents
    reason = refusal(settings, configured=configured(settings))
    if reason is None and spent >= cap:
        reason = AdvisorErrorCode.MONTHLY_CAP
    return AdvisorStatus(
        enabled=reason is None,
        reason=reason,
        provider=AdvisorProvider.ANTHROPIC,
        model=settings.advisor_model,
        month_spent_cents=display_cents(spent),
        month_cap_cents=cap,
        resets_on=next_month(today),
    )


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(session: DbSession, user: CurrentUser) -> list[ConversationSummary]:
    """The current user's conversations, newest first. Nobody sees anyone else's."""
    not_implemented("099")


@router.post(
    "/conversations", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED
)
def create_conversation(
    session: DbSession, user: CurrentUser, payload: ConversationCreate
) -> ConversationSummary:
    """Start a conversation in the Mine or Household view."""
    not_implemented("099")


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    session: DbSession, user: CurrentUser, conversation_id: uuid.UUID
) -> ConversationDetail:
    """A conversation with its turns, answers, figure checks, sources and lookups.

    Never the raw tool payloads: those stay in the transcript the loop replays.
    """
    not_implemented("099")


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    session: DbSession, user: CurrentUser, conversation_id: uuid.UUID
) -> Response:
    """Delete now, for good. Copies in backup files written before today remain."""
    not_implemented("099")


@router.post(
    "/conversations/{conversation_id}/turns",
    response_class=EventStreamResponse,
    responses=_EVENT_STREAM,
)
def create_turn(
    session: DbSession, user: CurrentUser, conversation_id: uuid.UUID, payload: TurnCreate
) -> Response:
    """Ask a question. The answer streams back as server-sent events."""
    not_implemented("099")


@router.put("/turns/{turn_id}/feedback", response_model=TurnRead)
def put_feedback(
    session: DbSession, user: CurrentUser, turn_id: uuid.UUID, payload: TurnFeedback
) -> TurnRead:
    """Mark an answer good or flagged, with an optional note, for the monthly review."""
    not_implemented("099")


@router.get(
    "/stream-check",
    response_class=EventStreamResponse,
    responses={200: {"description": "Three heartbeats, one second apart."}},
)
def stream_check(user: CurrentUser) -> Response:
    """Three heartbeats a second apart and nothing else.

    Proves events cross every proxy between here and the browser as they are written.
    Carries no data.
    """
    not_implemented("099")
