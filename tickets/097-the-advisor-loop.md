# 097 — The loop: turns, tools, budgets, caps, the kill switch, and the audit trail
Status: done
Wave: 10   Lane: L
Touches: none (implements `GET /advisor/status`, declared in 081)
Blocked by: 083, 095, 096
Read first: docs/ADVISOR.md#the-loop, docs/ADVISOR.md#cost, docs/ADVISOR.md#advice-guardrails, docs/adr/0010-the-advisor-loop-runs-in-the-api.md

## Goal
A question becomes a turn: the model is called, the tools it asks for run within budget, every call
is audited, caps are checked before money is spent, and everything that happened is persisted —
even when the turn fails or is cancelled. Proved end to end against the scripted model.

## Acceptance criteria
- [x] `advisor/prompts/system.md`: the static system prompt — role and limits; figures only from
      tools, copied as given, never computed; what a `_text` field is; scope rules and labelling;
      the formatting subset and screen tokens; advice guardrails; how to answer a request to change
      something. Its SHA-256 is the `prompt_version` recorded on every turn.
- [x] `advisor/loop.py` `run_turn(...)` yields `AdvisorEvent`s in the order ADVISOR.md#one-turn
      gives. Preconditions refuse with distinct codes: `disabled`, `demo`, `monthly_cap`,
      `conversation_cap`, `turn_in_progress`.
- [x] Today's date and the scope go in a per-turn context message, never the system prompt — or
      are prepended to the user turn on a model without mid-conversation system messages.
- [x] Every tool call goes through the 083 registry with a database audit sink; the turn budget in
      ADVISOR.md#one-turn is enforced; at eight model calls a final call is made with tools off.
- [x] Caps are checked **before** each model call from a worst-case estimate (input so far at the
      uncached rate plus `max_tokens` of output). Never after.
- [x] Stop reasons handled per ADVISOR.md#stop-reasons. A truncated `tool_use` is never executed.
- [x] Cancellation closes the model stream, marks the turn `cancelled`, and keeps the audit and
      usage rows already written.
- [x] `advisor/store.py`: persistence, each write its own short transaction; and **purge** —
      conversations 30 days after their last turn, tool calls after 90 days, usage after 13 months —
      run at the start of every advisor request, and as `make advisor-purge`.
- [x] `GET /advisor/status`: enabled or the refusal reason, month-to-date spend and the cap, the
      model.
- [x] Tests, all against `ScriptedModelClient`: a two-tool turn end to end; invalid arguments round
      trip; budget exhaustion; each cap refusing **before** any spend; the kill switch; a truncated
      tool call not run; a refusal; cancellation mid-stream; stored history replayed byte for byte
      on the next turn; purge boundaries.

## Files
- `api/app/advisor/loop.py` (new)
- `api/app/advisor/store.py` (new)
- `api/app/advisor/prompts/system.md` (new)
- `api/app/routers/advisor.py`
- `api/tests/test_advisor_loop.py`

## Notes
The streaming route does not use the request-scoped `get_session`; this is the deliberate exception
to ADR 0005 recorded in ADR 0010. Ordinary advisor routes — status, list, delete — use it as usual.

The system prompt is a file, not a string in code, so a change to it is a diff someone reads and a
change of `prompt_version` the eval gate notices.

## Done — 2026-09-28

- **Found and fixed: JSONB re-sorts object keys.** The byte-for-byte replay test failed because
  stored tool-call arguments came back in a different key order — a different prompt, and a lost
  cache. `advisor_messages.content` is now `JSON`, amended in 0007 before merge (095's note says
  why that was safe).
- A refused question starts no turn: it yields one `error` event and nothing else. `refused` as
  a turn status means **the model** declined.
- Only **complete** turns are replayed. A cancelled or failed turn can end on a tool call with no
  result, which the provider rejects.
- On a model without mid-conversation system messages, the context goes before the question —
  or **after** tool results, which must lead their message.
- The tools-off final call still sends every tool, with `tool_choice: none`: the tools are the
  start of the cached prefix, and history holds tool calls that need their definitions.
- Worst-case estimates: the last call's actual token total plus what was added since, at two
  bytes per token; the first call is estimated whole. Scripted and local calls cost nothing.
- Call ids carry across turns, read from the audit trail (which also holds a cancelled turn's
  calls).
- A turn left `streaming` for five minutes belongs to a dead process and is closed as failed
  when the next question arrives.
- `GET /advisor/status` purges first, then reports. `make advisor-purge` runs against the local
  database only; production purges itself on every advisor request.
- Answers carry citations but no figure checks yet (`grounding: none`); 098 adds them.
