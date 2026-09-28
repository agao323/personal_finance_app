"""The advisor: conversations, streamed turns, feedback, and whether it is on.

Declared by ticket 081, implemented by 097 and 099. The design is docs/ADVISOR.md, and the
constraints it answers to are docs/SECURITY.md#ai-agent.

**Each person sees only their own conversations.** Another member's conversation or turn is
a 404, never a 403: whether it exists is not theirs to learn.

**The streaming route is the one exception to ADR 0005** (ADR 0010). It checks ownership with
the request's session, then streams through its own short transactions — `advisor_store` —
because a turn outlives the request's transaction and its audit rows must survive a failure.
"""

from __future__ import annotations

import datetime as dt
import functools
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.advisor import policy, sse
from app.advisor.loop import MESSAGES, TurnDeps, configured, refusal, run_turn
from app.advisor.model import AnthropicModelClient, Effort, ModelClient
from app.advisor.pricing import display_cents
from app.advisor.sse import stream_events
from app.advisor.store import Store, fresh_transaction, nested_in, next_month
from app.advisor.tools import SessionScope, fresh_read_only_session, load_all
from app.advisor.transcript import render_turns
from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models.advisor import AdvisorConversation
from app.schemas.advisor import (
    AdvisorErrorCode,
    AdvisorEvent,
    AdvisorProvider,
    AdvisorStatus,
    ConversationCreate,
    ConversationDetail,
    ConversationSummary,
    ErrorEvent,
    TurnCreate,
    TurnFeedback,
    TurnRead,
)
from app.schemas.common import ErrorResponse, ViewScope

NEW_TITLE = "New conversation"
NO_CONVERSATION = "Conversation not found"
NO_TURN = "Turn not found"

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


def advisor_store() -> Store:
    """The streaming route's store: one short transaction per write."""
    return Store(fresh_transaction)


def advisor_tool_sessions() -> SessionScope:
    """Where tool calls read: a fresh read-only session each."""
    return fresh_read_only_session


@functools.cache
def _anthropic(api_key: str, model: str, effort: Effort, max_tokens: int) -> ModelClient:
    return AnthropicModelClient(api_key=api_key, model=model, effort=effort, max_tokens=max_tokens)


def advisor_client() -> ModelClient | None:
    """The configured model, or None when there is no key to call it with."""
    settings = get_settings()
    if not configured(settings) or settings.anthropic_api_key is None:
        return None
    return _anthropic(
        settings.anthropic_api_key.get_secret_value(),
        settings.advisor_model,
        settings.advisor_effort,
        settings.advisor_max_tokens,
    )


def purge_expired(session: DbSession) -> None:
    """Retention runs at the start of every advisor request (ADR 0012)."""
    Store(nested_in(session)).purge(dt.datetime.now(dt.UTC))


router.dependencies.append(Depends(purge_expired))


def _refuse_in_demo() -> None:
    if get_settings().demo_mode:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=MESSAGES[AdvisorErrorCode.DEMO])


def _summary(conversation: AdvisorConversation, turn_count: int) -> ConversationSummary:
    return ConversationSummary(
        id=conversation.id,
        view=ViewScope(conversation.view),
        title=conversation.title_text or NEW_TITLE,
        created_at=conversation.created_at,
        last_turn_at=conversation.last_turn_at,
        expires_at=conversation.expires_at,
        turn_count=turn_count,
    )


def _turns(session: Session, store: Store, conversation_id: uuid.UUID) -> list[TurnRead]:
    return render_turns(
        store.transcript(conversation_id),
        registry=load_all(),
        exempt_names=policy.household_names(session),
    )


@router.get("/status", response_model=AdvisorStatus)
def get_status(session: DbSession, user: CurrentUser) -> AdvisorStatus:
    """Whether a question can be asked now and, if not, why; and this month's spend."""
    settings = get_settings()
    store = Store(nested_in(session))
    today = dt.datetime.now(dt.UTC).date()
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
    _refuse_in_demo()
    return [_summary(c, n) for c, n in Store(nested_in(session)).conversations(user.id)]


@router.post(
    "/conversations", response_model=ConversationSummary, status_code=status.HTTP_201_CREATED
)
def create_conversation(
    session: DbSession, user: CurrentUser, payload: ConversationCreate
) -> ConversationSummary:
    """Start a conversation in the Mine or Household view."""
    _refuse_in_demo()
    store = Store(nested_in(session))
    created = store.create_conversation(user.id, payload.view, "", dt.datetime.now(dt.UTC))
    conversation = store.conversation(created, user.id)
    assert conversation is not None
    return _summary(conversation, 0)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    session: DbSession, user: CurrentUser, conversation_id: uuid.UUID
) -> ConversationDetail:
    """A conversation with its turns, answers, figure checks, sources and lookups.

    Never the raw tool payloads: those stay in the transcript the loop replays.
    """
    _refuse_in_demo()
    store = Store(nested_in(session))
    conversation = store.conversation(conversation_id, user.id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_CONVERSATION)
    turns = _turns(session, store, conversation.id)
    return ConversationDetail(**_summary(conversation, len(turns)).model_dump(), turns=turns)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    session: DbSession, user: CurrentUser, conversation_id: uuid.UUID
) -> Response:
    """Delete now, for good. Copies in backup files written before today remain."""
    _refuse_in_demo()
    if not Store(nested_in(session)).delete_conversation(conversation_id, user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_CONVERSATION)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/conversations/{conversation_id}/turns",
    response_class=EventStreamResponse,
    responses=_EVENT_STREAM,
)
async def create_turn(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    conversation_id: uuid.UUID,
    payload: TurnCreate,
    store: Annotated[Store, Depends(advisor_store)],
    tool_sessions: Annotated[SessionScope, Depends(advisor_tool_sessions)],
    client: Annotated[ModelClient | None, Depends(advisor_client)],
) -> Response:
    """Ask a question. The answer streams back as server-sent events."""
    _refuse_in_demo()
    checks = Store(nested_in(session))
    conversation = checks.conversation(conversation_id, user.id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_CONVERSATION)
    if checks.streaming(conversation.id, dt.datetime.now(dt.UTC)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=MESSAGES[AdvisorErrorCode.TURN_IN_PROGRESS]
        )

    events: AsyncIterator[BaseModel]
    settings = get_settings()
    reason = refusal(settings, configured=client is not None)
    if reason is not None or client is None:
        events = _only(
            ErrorEvent(
                type="error",
                code=reason or AdvisorErrorCode.NOT_CONFIGURED,
                message=MESSAGES[reason or AdvisorErrorCode.NOT_CONFIGURED],
            )
        )
    else:
        deps = TurnDeps(
            client=client,
            store=store,
            registry=load_all(),
            tool_sessions=tool_sessions,
            settings=settings,
        )
        events = run_turn(
            deps,
            conversation_id=conversation.id,
            user_id=user.id,
            view=ViewScope(conversation.view),
            question=payload.question,
        )
    return EventStreamResponse(
        stream_events(events, is_disconnected=request.is_disconnected), headers=sse.HEADERS
    )


async def _only(event: BaseModel) -> AsyncIterator[BaseModel]:
    yield event


@router.put("/turns/{turn_id}/feedback", response_model=TurnRead)
def put_feedback(
    session: DbSession, user: CurrentUser, turn_id: uuid.UUID, payload: TurnFeedback
) -> TurnRead:
    """Mark an answer good or flagged, with an optional note, for the monthly review."""
    _refuse_in_demo()
    store = Store(nested_in(session))
    turn = store.turn_for(turn_id, user.id)
    if turn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NO_TURN)
    store.set_feedback(
        turn.id, verdict=payload.verdict, note=payload.note, now=dt.datetime.now(dt.UTC)
    )
    return next(t for t in _turns(session, store, turn.conversation_id) if t.id == turn.id)


#: Seconds between `/stream-check` heartbeats. A module constant so a test can shorten it.
STREAM_CHECK_SECONDS = 1.0


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
    return EventStreamResponse(sse.heartbeats(3, STREAM_CHECK_SECONDS), headers=sse.HEADERS)
