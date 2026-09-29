"""One turn: a question in, events out, everything that happened written down.

docs/ADVISOR.md#one-turn is the specification; this is its implementation, in its order:

1. **Preconditions**, each a distinct refusal — the kill switch, the demo, a missing key, the
   monthly and conversation caps, a turn already streaming. A refused question starts no turn
   and yields one `error` event.
2. The question and a per-turn context message are stored; `turn_started` is emitted.
3. The request: the static system prompt (cached), the complete turns before this one replayed
   exactly as stored, this turn so far, and every tool.
4. Model calls, each **after** a cap check on its worst case. Text streams through as it
   arrives; tool calls are collected and run once the call ends.
5. Tool calls through the registry — validated, budgeted, read-only, audited in the database.
6. `end_turn` becomes an `answer`; every other stop reason becomes a specific `error`.
7. `turn_complete`, with what the turn cost.

The loop never reads the clock except through `now`, and `today` is fixed when the turn
starts and passed to every tool.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import datetime as dt
import hashlib
import json
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.advisor import answer as answer_module
from app.advisor import grounding, policy, pricing
from app.advisor.model import (
    ModelClient,
    ModelRequest,
    ModelResponse,
    TextDelta,
    ToolUse,
    supports_system_messages,
)
from app.advisor.store import Store, StoredMessage, TurnInProgressError, next_month
from app.advisor.tools import (
    CallIds,
    Registry,
    SessionScope,
    ToolContext,
    ToolDefinition,
    ToolOutcome,
    TurnBudget,
)
from app.config import Settings
from app.logging import get_logger
from app.observability import report_advisor_failure
from app.schemas.advisor import (
    AdvisorErrorCode,
    Answer,
    AnswerEvent,
    ErrorEvent,
    Grounding,
    PolicyNote,
    RegeneratingEvent,
    TextDeltaEvent,
    ToolCallEvent,
    TurnCompleteEvent,
    TurnStartedEvent,
    TurnStatus,
)
from app.schemas.common import ViewScope

logger = get_logger("advisor.loop")

PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"

#: Model calls per turn. The last is made with tools off: answer with what you have.
MAX_MODEL_CALLS = 8
#: Wall clock per turn.
TURN_SECONDS = 120.0
#: Bytes per token assumed when estimating a request not yet sent. Real text runs three
#: to four; two keeps the worst case a worst case.
BYTES_PER_TOKEN = 2

FINAL_CALL_CONTEXT = (
    "This turn has used all its lookups. Answer with what the lookups so far returned, "
    "and say what could not be checked."
)

MESSAGES: dict[AdvisorErrorCode, str] = {
    AdvisorErrorCode.DISABLED: "The advisor is switched off.",
    AdvisorErrorCode.DEMO: "The advisor is not available in the demo.",
    AdvisorErrorCode.NOT_CONFIGURED: "The advisor has no model configured.",
    AdvisorErrorCode.MONTHLY_CAP: "This month's advisor budget is used up.",
    AdvisorErrorCode.CONVERSATION_CAP: (
        "This conversation has reached its budget. Start a new one to keep going."
    ),
    AdvisorErrorCode.TURN_CAP: "This question reached its budget before an answer was ready.",
    AdvisorErrorCode.TURN_IN_PROGRESS: "An answer is still being written in this conversation.",
    AdvisorErrorCode.BUDGET_EXHAUSTED: "This question used all its lookups.",
    AdvisorErrorCode.TIMEOUT: "The answer took too long and was stopped.",
    AdvisorErrorCode.REFUSAL: "The model declined to answer this question.",
    AdvisorErrorCode.TRUNCATED: (
        "The answer was cut off before a lookup it needed could run. Try a narrower question."
    ),
    AdvisorErrorCode.CANCELLED: "Stopped.",
    AdvisorErrorCode.MODEL_ERROR: "The model could not be reached. Try again in a moment.",
}


@cache
def system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


@cache
def prompt_version() -> str:
    """The SHA-256 of the system prompt file, recorded on every turn."""
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()


def turn_context(today: dt.date, view: ViewScope) -> str:
    """Per-turn facts: today's date and the view. Context, not commands.

    Kept out of the system prompt, which is cached: the date changes daily and would
    invalidate the cache every day.
    """
    label = "Mine" if view is ViewScope.MINE else "Household"
    meaning = (
        "scoped figures are the signed-in person's ownership share of each account"
        if view is ViewScope.MINE
        else "scoped figures count every account in full"
    )
    return (
        f"Today is {today:%A} {today.isoformat()}. "
        f"This conversation's view is {label}: {meaning}. "
        "Spending, income and cash flow are household-wide in either view."
    )


def configured(settings: Settings) -> bool:
    """Whether the configured provider can be called: see `Settings.advisor_provider_ready`."""
    return settings.advisor_provider_ready


def refusal(settings: Settings, *, configured: bool) -> AdvisorErrorCode | None:
    """Why no question can be asked right now, before any spend is considered."""
    if settings.demo_mode:
        return AdvisorErrorCode.DEMO
    if not settings.advisor_enabled:
        return AdvisorErrorCode.DISABLED
    if not configured:
        return AdvisorErrorCode.NOT_CONFIGURED
    return None


# ── messages ──────────────────────────────────────────────────────────────────


_API_ROLE = {"user": "user", "tool_results": "user", "assistant": "assistant", "context": "system"}


def to_api_messages(
    stored: Sequence[StoredMessage], *, system_messages: bool
) -> list[dict[str, Any]]:
    """Stored messages as the provider takes them, content unchanged.

    `context` messages are mid-conversation system messages on a model that supports them.
    On one that does not, their text is put in front of the user message they follow — the
    same words, in the user turn, which is where such a model reads them.
    """
    out: list[dict[str, Any]] = []
    for message in stored:
        role = _API_ROLE[message.role]
        if role == "system" and not system_messages:
            if out and out[-1]["role"] == "user":
                before = out[-1]["content"]
                # Tool results must lead the message that answers a tool call.
                if any(block.get("type") == "tool_result" for block in before):
                    merged = [*before, *message.content]
                else:
                    merged = [*message.content, *before]
                out[-1] = {"role": "user", "content": merged}
                continue
            role = "user"
        out.append({"role": role, "content": message.content})
    return out


def _estimate_tokens(payload: Any) -> int:
    size = len(json.dumps(payload, separators=(",", ":"), default=str).encode())
    return size // BYTES_PER_TOKEN + 1


def _tools_payload(tools: Sequence[ToolDefinition]) -> list[dict[str, Any]]:
    return [dataclasses.asdict(tool) for tool in tools]


# ── the turn ──────────────────────────────────────────────────────────────────


@dataclass
class TurnDeps:
    """What a turn needs from outside. Everything with a side effect comes in here."""

    client: ModelClient
    store: Store
    registry: Registry
    #: Read-only sessions for tool calls: `fresh_read_only_session` in production.
    tool_sessions: SessionScope
    settings: Settings
    now: Callable[[], dt.datetime] = field(default=lambda: dt.datetime.now(dt.UTC))
    turn_seconds: float = TURN_SECONDS
    max_model_calls: int = MAX_MODEL_CALLS


class _TurnError(Exception):
    """Ends a turn with a specific error code."""

    def __init__(self, code: AdvisorErrorCode, status: TurnStatus = TurnStatus.FAILED) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass
class _DbAudit:
    store: Store
    conversation_id: uuid.UUID
    turn_id: uuid.UUID

    def record(self, outcome: ToolOutcome) -> None:
        self.store.record_tool_call(self.conversation_id, self.turn_id, outcome)


def _renderings(history: Sequence[StoredMessage]) -> list[str]:
    """Every tool result the model saw in earlier turns, as it saw it."""
    return [
        block["content"]
        for message in history
        if message.role == "tool_results"
        for block in message.content
        if isinstance(block.get("content"), str)
    ]


def retry_context(unverified: Sequence[str], notes: Sequence[PolicyNote]) -> str:
    """The operator message for the one regeneration: what failed, stated as facts."""
    parts = ["The previous answer was not shown to the person."]
    if unverified:
        listed = "; ".join(dict.fromkeys(unverified))
        parts.append(
            f"These figures in it did not come from a lookup: {listed}. Every figure is "
            "written as a reference to a lookup result, such as {{c2.net_worth}}, or comes "
            "from a tool that computes it; a figure no tool produced is left out."
        )
    parts.extend(f"It also broke a rule: {note.message}" for note in notes)
    parts.append("Write the answer again.")
    return " ".join(parts)


def _regenerating(notes: Sequence[PolicyNote]) -> str:
    if notes:
        return "The answer broke one of the advisor's rules and is being written again."
    return "A figure could not be traced to a lookup, so the answer is being written again."


def _text_of(content: Sequence[dict[str, Any]]) -> str:
    return "".join(block.get("text", "") for block in content if block.get("type") == "text")


def _error(code: AdvisorErrorCode, resets_on: dt.date | None = None) -> ErrorEvent:
    return ErrorEvent(type="error", code=code, message=MESSAGES[code], resets_on=resets_on)


async def run_turn(
    deps: TurnDeps,
    *,
    conversation_id: uuid.UUID,
    user_id: int,
    view: ViewScope,
    question: str,
    instructions: str | None = None,
) -> AsyncIterator[BaseModel]:
    """Answer one question. Yields `AdvisorEvent` members in docs/ADVISOR.md#one-turn order.

    `instructions` travel with this turn's context message — a monthly review's fixed prompt
    (plan 119) — and are replayed with it, never shown as the question.
    """
    settings = deps.settings
    store = deps.store
    started_at = deps.now()
    today = started_at.date()
    resets_on = next_month(today)

    refused = refusal(settings, configured=True)
    if refused is not None:
        yield _error(refused)
        return

    store.purge(started_at)
    context = turn_context(today, view)
    if instructions:
        context = f"{context}\n\n{instructions}"

    # Worst case of the first call, for the precondition caps: everything sent at the
    # uncached rate, plus a full `max_tokens` of output.
    tools = deps.registry.definitions()
    prefix_tokens = _estimate_tokens([system_prompt(), _tools_payload(tools)])
    replayed = [m.content for m in store.history(conversation_id, before_seq=2**31 - 1)]
    first_call = _worst_case(
        deps, prefix_tokens + _estimate_tokens([replayed, question, context]), today
    )
    if store.month_spent(today) + first_call > settings.advisor_monthly_cap_cents:
        yield _error(AdvisorErrorCode.MONTHLY_CAP, resets_on)
        return
    if (
        store.conversation_spent(conversation_id) + first_call
        > settings.advisor_conversation_cap_cents
    ):
        yield _error(AdvisorErrorCode.CONVERSATION_CAP)
        return

    try:
        turn = store.start_turn(
            conversation_id,
            question=question,
            context=context,
            now=started_at,
            model=deps.client.model,
            prompt_version=prompt_version(),
        )
    except TurnInProgressError:
        yield _error(AdvisorErrorCode.TURN_IN_PROGRESS)
        return

    yield TurnStartedEvent(
        type="turn_started", turn_id=turn.turn_id, conversation_id=conversation_id
    )

    ctx = ToolContext(
        today=today,
        user_id=user_id,
        view=view,
        sessions=deps.tool_sessions,
        budget=TurnBudget(),
        audit=_DbAudit(store, conversation_id, turn.turn_id),
        call_ids=CallIds(issued=store.calls_issued(conversation_id)),
    )
    deadline = time.monotonic() + deps.turn_seconds
    outcomes: list[ToolOutcome] = []
    served: str | None = None
    status = TurnStatus.FAILED
    checked_as = Grounding.NONE
    finished = False

    try:
        history = store.history(conversation_id, before_seq=turn.seq)
        # What earlier turns proved is rebuilt from their stored results, so a figure from
        # the last question can be referred to in this one.
        evidence = grounding.Evidence()
        evidence.add_all(_renderings(history))
        with deps.tool_sessions() as session:
            names = policy.household_names(session)
        regenerated = False
        this_turn: list[StoredMessage] = [
            StoredMessage(turn.turn_id, "user", [{"type": "text", "text": question}]),
            StoredMessage(turn.turn_id, "context", [{"type": "text", "text": context}]),
        ]
        # The input tokens already known from the last call's usage; what has been added
        # since is estimated from its size.
        known_tokens: int | None = None
        sent = 0
        calls = 0
        while True:
            calls += 1
            final_call = calls >= deps.max_model_calls
            if final_call:
                note = [{"type": "text", "text": FINAL_CALL_CONTEXT}]
                store.add_message(turn.turn_id, "context", note)
                this_turn.append(StoredMessage(turn.turn_id, "context", note))

            messages = to_api_messages(
                [*history, *this_turn], system_messages=supports_system_messages(deps.client.model)
            )
            request = ModelRequest(
                system=[system_prompt()],
                messages=messages,
                tools=tools,
                tools_enabled=not final_call,
            )
            if known_tokens is None:
                estimate = prefix_tokens + _estimate_tokens(messages)
            else:
                estimate = known_tokens + _estimate_tokens([m.content for m in this_turn[sent:]])
            _check_caps(
                deps, conversation_id, turn.turn_id, _worst_case(deps, estimate, today), today
            )
            sent = len(this_turn)

            response: ModelResponse | None = None
            tool_uses: list[ToolUse] = []
            resolver = grounding.StreamResolver(evidence)
            call_started = time.monotonic()
            async with contextlib.aclosing(
                _bounded(deps.client.stream(request), deadline)
            ) as events:
                async for event in events:
                    if isinstance(event, TextDelta):
                        shown = resolver.feed(event.text)
                        if shown:
                            yield TextDeltaEvent(type="text_delta", text=shown)
                    elif isinstance(event, ToolUse):
                        tool_uses.append(event)
                    else:
                        response = event
            held = resolver.flush()
            if held:
                yield TextDeltaEvent(type="text_delta", text=held)
            if response is None:
                raise _TurnError(AdvisorErrorCode.MODEL_ERROR)

            served = response.model
            store.record_usage(
                turn.turn_id,
                provider=deps.client.provider,
                model=response.model,
                request_id=response.request_id,
                usage=response.usage,
                stop_reason=response.stop_reason,
                latency_ms=round((time.monotonic() - call_started) * 1000),
            )
            store.add_message(turn.turn_id, "assistant", response.content)
            this_turn.append(StoredMessage(turn.turn_id, "assistant", response.content))
            sent = len(this_turn)
            u = response.usage
            known_tokens = (
                u.input_tokens
                + u.cache_write_5m_tokens
                + u.cache_write_1h_tokens
                + u.cache_read_tokens
                + u.output_tokens
            )

            if response.stop_reason == "tool_use" and tool_uses and not final_call:
                results: list[dict[str, Any]] = []
                for tool_use in tool_uses:
                    if time.monotonic() >= deadline:
                        raise _TurnError(AdvisorErrorCode.TIMEOUT)
                    outcome = await asyncio.to_thread(
                        deps.registry.run, tool_use.name, tool_use.input, ctx
                    )
                    outcomes.append(outcome)
                    evidence.add(outcome.content)
                    # Ids, the tool, and counts. Never arguments, results or the question.
                    logger.info(
                        "advisor_tool_call",
                        turn_id=str(turn.turn_id),
                        tool=outcome.tool,
                        status=outcome.status.value,
                        latency_ms=outcome.latency_ms,
                        row_count=outcome.row_count,
                    )
                    yield ToolCallEvent(type="tool_call", lookup=answer_module.lookup(outcome))
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": outcome.content,
                            **({"is_error": True} if outcome.is_error else {}),
                        }
                    )
                store.add_message(turn.turn_id, "tool_results", results)
                this_turn.append(StoredMessage(turn.turn_id, "tool_results", results))
                continue

            if response.stop_reason == "end_turn" or (
                response.stop_reason == "max_tokens" and not tool_uses
            ):
                truncated = response.stop_reason == "max_tokens"
                checked = grounding.check(
                    answer_module.clean(_text_of(response.content)), evidence, question=question
                )
                notes = policy.check(
                    checked.text, figures=checked.figures, evidence=evidence, exempt_names=names
                )
                failed = bool(checked.unverified or notes)
                if failed and not regenerated and not final_call and not truncated:
                    # One regeneration, told what failed. The streamed text is discarded.
                    regenerated = True
                    retry = [{"type": "text", "text": retry_context(checked.unverified, notes)}]
                    store.add_message(turn.turn_id, "context", retry)
                    this_turn.append(StoredMessage(turn.turn_id, "context", retry))
                    yield RegeneratingEvent(type="regenerating", reason=_regenerating(notes))
                    continue
                checked_as = (
                    Grounding.FLAGGED
                    if failed
                    else Grounding.VERIFIED
                    if checked.figures
                    else Grounding.NONE
                )
                answer = Answer(
                    text=checked.text,
                    figures=checked.figures,
                    citations=answer_module.citations(outcomes),
                    limitations=answer_module.limitations(outcomes),
                    policy_notes=notes,
                    truncated=truncated,
                )
                yield AnswerEvent(type="answer", answer=answer)
                status = TurnStatus.COMPLETE
                break
            if response.stop_reason == "max_tokens":
                # A tool call cut off mid-arguments. Never run it.
                raise _TurnError(AdvisorErrorCode.TRUNCATED)
            if response.stop_reason == "refusal":
                raise _TurnError(AdvisorErrorCode.REFUSAL, TurnStatus.REFUSED)
            # `pause_turn` (no server tools are declared, so never expected), a tool call on
            # the tools-off final call, or anything new.
            logger.warning(
                "advisor_unexpected_stop",
                turn_id=str(turn.turn_id),
                stop_reason=response.stop_reason,
            )
            raise _TurnError(AdvisorErrorCode.MODEL_ERROR)

        store.finish_turn(
            turn.turn_id, status=status, now=deps.now(), grounding=checked_as, model=served
        )
        finished = True
    except _TurnError as stop:
        status = stop.status
        store.finish_turn(
            turn.turn_id, status=stop.status, now=deps.now(), error=stop.code, model=served
        )
        finished = True
        yield _error(stop.code, resets_on if stop.code is AdvisorErrorCode.MONTHLY_CAP else None)
    except (asyncio.CancelledError, GeneratorExit):
        # The browser went away. The model stream is already closed — `aclosing` closed it
        # on the way out — and every audit and usage row written so far stays.
        store.finish_turn(
            turn.turn_id,
            status=TurnStatus.CANCELLED,
            now=deps.now(),
            error=AdvisorErrorCode.CANCELLED,
            model=served,
        )
        finished = True
        raise
    except Exception as exc:
        # The provider's errors, and ours. The class, never the message.
        logger.warning("advisor_turn_failed", turn_id=str(turn.turn_id), error=type(exc).__name__)
        report_advisor_failure("turn", type(exc).__name__, turn_id=str(turn.turn_id))
        store.finish_turn(
            turn.turn_id,
            status=TurnStatus.FAILED,
            now=deps.now(),
            error=AdvisorErrorCode.MODEL_ERROR,
            model=served,
        )
        finished = True
        yield _error(AdvisorErrorCode.MODEL_ERROR)
    finally:
        if not finished:
            store.finish_turn(turn.turn_id, status=TurnStatus.FAILED, now=deps.now(), model=served)

    logger.info(
        "advisor_turn_finished",
        turn_id=str(turn.turn_id),
        status=status.value,
        grounding=checked_as.value,
        tool_calls=len(outcomes),
    )
    yield TurnCompleteEvent(
        type="turn_complete",
        turn_id=turn.turn_id,
        grounding=checked_as,
        cost_cents=pricing.display_cents(store.turn_spent(turn.turn_id)),
        month_spent_cents=pricing.display_cents(store.month_spent(today)),
    )


def _worst_case(deps: TurnDeps, input_tokens: int, today: dt.date) -> Decimal:
    """Cents, if every input token were uncached and the output ran to `max_tokens`."""
    if deps.client.provider in pricing.FREE_PROVIDERS:
        return Decimal(0)
    price = pricing.price_for(deps.client.model, today)
    per_token = Decimal(100) / Decimal(1_000_000)
    return (
        price.input * input_tokens + price.output * deps.settings.advisor_max_tokens
    ) * per_token


def _check_caps(
    deps: TurnDeps, conversation_id: uuid.UUID, turn_id: uuid.UUID, worst: Decimal, today: dt.date
) -> None:
    """Before a model call, never after: refuse if its worst case would cross any cap."""
    store, settings = deps.store, deps.settings
    if store.turn_spent(turn_id) + worst > settings.advisor_turn_cap_cents:
        raise _TurnError(AdvisorErrorCode.TURN_CAP)
    if store.conversation_spent(conversation_id) + worst > settings.advisor_conversation_cap_cents:
        raise _TurnError(AdvisorErrorCode.CONVERSATION_CAP)
    if store.month_spent(today) + worst > settings.advisor_monthly_cap_cents:
        raise _TurnError(AdvisorErrorCode.MONTHLY_CAP)


async def _bounded(stream: AsyncIterator[Any], deadline: float) -> AsyncGenerator[Any]:
    """The model's events, until the turn's deadline. Always closes the stream behind it."""
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _TurnError(AdvisorErrorCode.TIMEOUT)
            try:
                event = await asyncio.wait_for(anext(stream), remaining)
            except StopAsyncIteration:
                return
            except TimeoutError:
                raise _TurnError(AdvisorErrorCode.TIMEOUT) from None
            yield event
    finally:
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            await aclose()
