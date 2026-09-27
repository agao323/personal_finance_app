# 107 — Switch it on: the advisor in production
Status: todo
Wave: 10   Lane: —
Touches: none (configuration, a runbook, and records)
Blocked by: 099, 100, 102, 103, 105, 106 — and the gates in DECISIONS.md, 2026-09-27
Read first: docs/DECISIONS.md, docs/ADVISOR.md#cost, docs/runbooks/going-live.md

## Goal
`ADVISOR_ENABLED=true` on pfa-api, with every gate met and recorded, the kill switch proved, and a
runbook for the day something goes wrong.

## Acceptance criteria
- [ ] **Gates** recorded as met: ADR 0008's restore drill against production; ADR 0009 accepted;
      103 done.
- [ ] Anthropic Console: a `pfa-prod` workspace with a **$25 monthly spend limit** and its own key;
      a `pfa-eval` workspace with its own key and limit.
- [ ] A passing `make eval` at `n=3`, at the model, effort and prompt version being deployed,
      recorded in ADVISOR.md#eval-runs.
- [ ] `fly secrets set -a pfa-api ANTHROPIC_API_KEY=… ADVISOR_ENABLED=true`. The key is set on
      pfa-api and nowhere else.
- [ ] Through Cloudflare, in a browser: `/api/advisor/stream-check` events arrive about a second
      apart, not together at the end. Recorded.
- [ ] **Kill-switch drill**: set `ADVISOR_ENABLED=false`; a question is refused as switched off and
      the Insights panel still works; set it back. Recorded with timings.
- [ ] **Cancellation drill**: stop an answer mid-stream; `advisor_usage` shows no model call after
      the stop. Recorded.
- [ ] After the first week: tools used, rows returned, `withheld_count` totals, cost against the
      estimate, and the `note_limitation` ranking — written into ADVISOR.md#cost and ticket 080, and
      used to order Waves 11 and 12.
- [ ] `docs/runbooks/advisor.md`: enabling and disabling; rotating the key; reading month-to-date
      spend; running `make advisor-purge`; and on a suspected injection — switch off, find the
      turn's tool calls, find the withheld rows by table and id, fix or remove the source text.

## Files
- `docs/runbooks/advisor.md` (new)
- `docs/ADVISOR.md`
- `docs/adr/0009-advisor-model-provider.md` (status to accepted)

## Notes
The same shape as ticket 037's infrastructure half: the code is done before this starts, and this
ticket is the owner's hands on the dashboards plus the records that prove it was done. Nothing here
is authorable by a session.
