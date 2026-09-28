"""A stored conversation, rendered for the screen: questions, checked answers, sources, lookups.

**Answers are rebuilt, not stored.** The transcript holds what the model saw and wrote; the
answer a person saw is a deterministic function of it — `answer.clean`, then
`grounding.check` against the conversation's results so far, then `policy.check`. Rebuilding
means one source of truth, and a fix to the checker applies to old answers too.

**Raw tool payloads never leave.** A turn carries its lookups — tool, a summary of the
arguments, rows, time, as-of — and its sources, never the results the model read.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable
from typing import Any

from app.advisor import answer, grounding, policy
from app.advisor.store import Transcript, TranscriptTurn
from app.advisor.tools import Registry, summarize
from app.models.advisor import AdvisorToolCall
from app.schemas.advisor import (
    AdvisorErrorCode,
    Answer,
    Citation,
    Feedback,
    Grounding,
    LimitationKind,
    Lookup,
    LookupStatus,
    TurnRead,
    TurnStatus,
)
from app.schemas.common import ViewScope


def _text(blocks: Iterable[dict[str, Any]]) -> str:
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def _envelopes(turn: TranscriptTurn) -> dict[str, dict[str, Any]]:
    """Call id → the envelope of its stored result: as-of, view, stale."""
    found: dict[str, dict[str, Any]] = {}
    for message in turn.messages:
        if message.role != "tool_results":
            continue
        for block in message.content:
            try:
                envelope = json.loads(block.get("content", ""))
            except (TypeError, ValueError):
                continue
            if isinstance(envelope, dict) and "call" in envelope:
                found[str(envelope["call"])] = envelope
    return found


def _lookup(call: AdvisorToolCall, envelope: dict[str, Any], registry: Registry) -> Lookup:
    as_of = envelope.get("as_of")
    return Lookup(
        call_id=call.tool_call_id,
        tool=call.tool_name,
        label=registry.label(call.tool_name, call.args),
        arguments=summarize(call.args),
        status=LookupStatus(call.status),
        row_count=call.row_count,
        latency_ms=call.latency_ms,
        as_of=dt.date.fromisoformat(as_of) if as_of else None,
    )


def render_turns(
    transcript: Transcript, *, registry: Registry, exempt_names: Iterable[str]
) -> list[TurnRead]:
    names = list(exempt_names)
    evidence = grounding.Evidence()
    rendered: list[TurnRead] = []
    for turn in transcript.turns:
        envelopes = _envelopes(turn)
        for envelope_text in (
            block["content"]
            for m in turn.messages
            if m.role == "tool_results"
            for block in m.content
            if isinstance(block.get("content"), str)
        ):
            evidence.add(envelope_text)

        question = next((_text(m.content) for m in turn.messages if m.role == "user"), "")
        lookups = [_lookup(c, envelopes.get(c.tool_call_id, {}), registry) for c in turn.calls]
        final = next((m for m in reversed(turn.messages) if m.role == "assistant"), None)
        built: Answer | None = None
        if turn.turn.status == TurnStatus.COMPLETE and final is not None:
            checked = grounding.check(
                answer.clean(_text(final.content)), evidence, question=question
            )
            built = Answer(
                text=checked.text,
                figures=checked.figures,
                citations=[
                    Citation(
                        call_id=lk.call_id,
                        tool=lk.tool,
                        label=lk.label,
                        as_of=lk.as_of,
                        view=_view(envelopes.get(lk.call_id, {})),
                        stale=bool(envelopes.get(lk.call_id, {}).get("stale")),
                    )
                    for lk in lookups
                    if lk.status is LookupStatus.OK and lk.tool != answer.NOTE_LIMITATION
                ],
                limitations=list(
                    dict.fromkeys(
                        LimitationKind(c.args["capability"])
                        for c in turn.calls
                        if c.tool_name == answer.NOTE_LIMITATION and c.status == LookupStatus.OK
                    )
                ),
                policy_notes=policy.check(
                    checked.text, figures=checked.figures, evidence=evidence, exempt_names=names
                ),
                truncated=turn.last_stop == "max_tokens",
            )
        t = turn.turn
        rendered.append(
            TurnRead(
                id=t.id,
                seq=t.seq,
                question=question,
                status=TurnStatus(t.status),
                grounding=Grounding(t.grounding),
                answer=built,
                lookups=lookups,
                error=AdvisorErrorCode(t.error_code) if t.error_code else None,
                feedback=Feedback(t.feedback) if t.feedback else None,
                feedback_note=t.feedback_note_text,
                started_at=t.started_at,
                finished_at=t.finished_at,
            )
        )
    return rendered


def _view(envelope: dict[str, Any]) -> ViewScope | None:
    view = envelope.get("view")
    return ViewScope(view) if view else None
