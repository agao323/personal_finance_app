# 097 — The loop: turns, tools, budgets, caps, the kill switch, and the audit trail
Status: todo
Wave: 10   Lane: L
Touches: none (implements `GET /advisor/status`, declared in 081)
Blocked by: 083, 095, 096
Read first: docs/ADVISOR.md#the-loop, docs/ADVISOR.md#cost, docs/ADVISOR.md#advice-guardrails, docs/adr/0010-the-advisor-loop-runs-in-the-api.md

## Goal
A question becomes a turn: the model is called, the tools it asks for run within budget, every call
is audited, caps are checked before money is spent, and everything that happened is persisted —
even when the turn fails or is cancelled. Proved end to end against the scripted model.

## Acceptance criteria
- [ ] `advisor/prompts/system.md`: the static system prompt — role and limits; figures only from
      tools, copied as given, never computed; what a `_text` field is; scope rules and labelling;
      the formatting subset and screen tokens; advice guardrails; how to answer a request to change
      something. Its SHA-256 is the `prompt_version` recorded on every turn.
- [ ] `advisor/loop.py` `run_turn(...)` yields `AdvisorEvent`s in the order ADVISOR.md#one-turn
      gives. Preconditions refuse with distinct codes: `disabled`, `demo`, `monthly_cap`,
      `conversation_cap`, `turn_in_progress`.
- [ ] Today's date and the scope go in a per-turn context message, never the system prompt — or
      are prepended to the user turn on a model without mid-conversation system messages.
- [ ] Every tool call goes through the 083 registry with a database audit sink; the turn budget in
      ADVISOR.md#one-turn is enforced; at eight model calls a final call is made with tools off.
- [ ] Caps are checked **before** each model call from a worst-case estimate (input so far at the
      uncached rate plus `max_tokens` of output). Never after.
- [ ] Stop reasons handled per ADVISOR.md#stop-reasons. A truncated `tool_use` is never executed.
- [ ] Cancellation closes the model stream, marks the turn `cancelled`, and keeps the audit and
      usage rows already written.
- [ ] `advisor/store.py`: persistence, each write its own short transaction; and **purge** —
      conversations 30 days after their last turn, tool calls after 90 days, usage after 13 months —
      run at the start of every advisor request, and as `make advisor-purge`.
- [ ] `GET /advisor/status`: enabled or the refusal reason, month-to-date spend and the cap, the
      model.
- [ ] Tests, all against `ScriptedModelClient`: a two-tool turn end to end; invalid arguments round
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
