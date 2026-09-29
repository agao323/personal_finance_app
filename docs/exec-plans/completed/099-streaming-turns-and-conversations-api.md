# 099 — The streaming turn endpoint, and the conversations API
Status: done
Wave: 10   Lane: L
Touches: none (implements routes declared in 081)
Blocked by: 097, 098
Read first: docs/ADVISOR.md#request-path, docs/adr/0010-the-advisor-loop-runs-in-the-api.md

## Goal
A question posted to a conversation streams back as server-sent events, survives the proxies
between here and a phone, and stops costing money the moment the phone gives up.

## Acceptance criteria
- [x] `POST /advisor/conversations/{id}/turns` returns `text/event-stream` of `AdvisorEvent` JSON,
      with `Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no`. `turn_started` is
      the first write; `heartbeat` every 15 s; the turn is capped at 120 s of wall clock.
- [x] A client disconnect cancels the loop (097's cancellation path) — detected between events and
      on a failed send.
- [x] One streaming turn per conversation; a second gets `409`.
- [x] `GET POST /advisor/conversations`: list and create, **the current user's only**.
      `GET /advisor/conversations/{id}`: rendered turns — question, answer, figure checks,
      citations, limitations — never raw tool payloads. `DELETE`: immediate, hard; `404` for
      another member's conversation.
- [x] The conversation detail includes each turn's **lookups** (tool, arguments summary, rows,
      latency, as-of) for the "show lookups" control, and its feedback.
- [x] `PUT /advisor/turns/{turn_id}/feedback` records `good` or `flagged` with an optional note on
      the current user's own turn; `404` for anyone else's.
- [x] `GET /advisor/stream-check`: three heartbeats one second apart, nothing else.
- [x] Under `DEMO_MODE` every advisor route refuses with reason `demo`; the middleware already
      turns POST and DELETE into `405`.
- [x] Tests: an httpx streaming client reads the full event sequence of a scripted turn; heartbeats
      against a slow scripted model with the clock controlled; a disconnect leaves the turn
      `cancelled`; the 409; two users cannot see or delete each other's conversations; delete
      leaves the audit rows.

## Files
- `api/app/routers/advisor.py`
- `api/app/advisor/sse.py` (new)
- `api/tests/test_api_advisor.py`

## Notes
Decision 5 on plan 122 — each person sees their own conversations — is what the list's
filtering implements. If the owner chooses shared conversations instead, drop the filter and the
404; nothing else changes.

## Done — 2026-09-28

- The turn runs in **one task** feeding a queue; the SSE generator reads the queue with a 1 s
  poll, sends a heartbeat after 15 s of quiet, and on a disconnect (polled between events, or a
  failed send) cancels that task — 097's cancellation path. The model's HTTP stream is opened
  and closed in the same task.
- The streaming route checks ownership and the 409 with the request's session, then streams
  through `advisor_store` (one short transaction per write). The store, the tool sessions and
  the model are dependencies, so tests point them at the rolled-back session and the scripted
  model; nothing else differs from production.
- **Answers are rebuilt, not stored** (`advisor/transcript.py`): the detail route re-runs
  clean → check → policy over the stored transcript. One source of truth, and a checker fix
  applies to old answers too. Lookups come from the audit rows, as-of and view from the stored
  result envelopes; raw payloads never leave.
- A conversation starts titled "New conversation" and takes its first question as its title.
- Under `DEMO_MODE`: status says `demo`; GETs are 403 with the demo message; the middleware
  already makes every write 405.
- `starlette.testclient` buffers a streamed body, so the disconnect is tested at the SSE layer
  with the real loop and a slow model. Ticket 100 proves the real hops.
- No stubbed routes remain; `test_every_stub_returns_501` now has nothing to parametrise.
