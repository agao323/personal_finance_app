# 099 — The streaming turn endpoint, and the conversations API
Status: todo
Wave: 10   Lane: L
Touches: none (implements routes declared in 081)
Blocked by: 097, 098
Read first: docs/ADVISOR.md#request-path, docs/adr/0010-the-advisor-loop-runs-in-the-api.md

## Goal
A question posted to a conversation streams back as server-sent events, survives the proxies
between here and a phone, and stops costing money the moment the phone gives up.

## Acceptance criteria
- [ ] `POST /advisor/conversations/{id}/turns` returns `text/event-stream` of `AdvisorEvent` JSON,
      with `Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no`. `turn_started` is
      the first write; `heartbeat` every 15 s; the turn is capped at 120 s of wall clock.
- [ ] A client disconnect cancels the loop (097's cancellation path) — detected between events and
      on a failed send.
- [ ] One streaming turn per conversation; a second gets `409`.
- [ ] `GET POST /advisor/conversations`: list and create, **the current user's only**.
      `GET /advisor/conversations/{id}`: rendered turns — question, answer, figure checks,
      citations, limitations — never raw tool payloads. `DELETE`: immediate, hard; `404` for
      another member's conversation.
- [ ] The conversation detail includes each turn's **lookups** (tool, arguments summary, rows,
      latency, as-of) for the "show lookups" control, and its feedback.
- [ ] `PUT /advisor/turns/{turn_id}/feedback` records `good` or `flagged` with an optional note on
      the current user's own turn; `404` for anyone else's.
- [ ] `GET /advisor/stream-check`: three heartbeats one second apart, nothing else.
- [ ] Under `DEMO_MODE` every advisor route refuses with reason `demo`; the middleware already
      turns POST and DELETE into `405`.
- [ ] Tests: an httpx streaming client reads the full event sequence of a scripted turn; heartbeats
      against a slow scripted model with the clock controlled; a disconnect leaves the turn
      `cancelled`; the 409; two users cannot see or delete each other's conversations; delete
      leaves the audit rows.

## Files
- `api/app/routers/advisor.py`
- `api/app/advisor/sse.py` (new)
- `api/tests/test_api_advisor.py`

## Notes
Decision 5 on ticket 080 — each person sees their own conversations — is what the list's
filtering implements. If the owner chooses shared conversations instead, drop the filter and the
404; nothing else changes.
