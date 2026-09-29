# 119 — The monthly review, on request and in the app only (optional)
Status: todo — optional; build only if the owner wants it after using Wave 10
Wave: 13   Lane: —
Touches: **contract** (`ConversationCreate` gains `kind`)
Blocked by: 107, 111
Read first: docs/ADVISOR.md#decisions, docs/DECISIONS.md

## Goal
Once a month the advisor offers a review of the month just ended — spending against last month and
against limits, subscriptions that changed, credits used and missed, runway, net worth and why it
moved — generated only when asked, and read in the app.

## Acceptance criteria
- [ ] On the first visit to `/advisor` in a new month, an offer: "Review September — about $0.15."
      Nothing is generated until it is accepted.
- [ ] A review is a conversation of `kind: review`, started with a fixed prompt that calls
      `findings_list`, `spend_compare` (last month against the one before), `cashflow_get`,
      `cards_value` and `networth_explain_change`. Follow-up questions work as in any
      conversation; the same caps, grounding and retention apply.
- [ ] **No email, no push, no scheduler.** A notification is egress, and a scheduled job is the
      thing ADR 0008 learned not to trust.
- [ ] Three review eval cases: every section present, every figure grounded.
- [ ] Tests: the offer appears once per month and not after acceptance; a review conversation is
      listed and deleted like any other.

## Files
- `api/app/schemas/advisor.py`, `api/app/routers/advisor.py`
- `api/app/advisor/prompts/review.md` (new)
- `web/src/components/advisor/review-offer.tsx` (new)
- `api/evals/cases/review.yaml` (new)

## Notes
The review is what makes the advisor pass PRODUCT's monthly-use test on its own. If Wave 10's chat
turns out to be used weekly anyway, this is not needed.
