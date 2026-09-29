# 119 — The monthly review, on request and in the app only
Status: done
Wave: 13   Lane: —
Touches: **contract** (`ConversationCreate` gains `kind`)
Blocked by: 107, 111
Read first: docs/ADVISOR.md#decisions, docs/DECISIONS.md

## Goal
Once a month the advisor offers a review of the month just ended — spending against last month and
against limits, subscriptions that changed, credits used and missed, runway, net worth and why it
moved — generated only when asked, and read in the app.

## Acceptance criteria
- [x] On the first visit to `/advisor` in a new month, an offer: "Review September — about $0.15."
      Nothing is generated until it is accepted.
- [x] A review is a conversation of `kind: review`, started with a fixed prompt that calls
      `findings_list`, `spend_compare` (last month against the one before), `cashflow_get`,
      `cards_value` and `networth_explain_change`. Follow-up questions work as in any
      conversation; the same caps, grounding and retention apply.
- [x] **No email, no push, no scheduler.** A notification is egress, and a scheduled job is the
      thing ADR 0008 learned not to trust.
- [x] Three review eval cases: every section present, every figure grounded.
- [x] Tests: the offer appears once per month and not after acceptance; a review conversation is
      listed and deleted like any other.

## Files
- `api/app/schemas/advisor.py`, `api/app/routers/advisor.py`
- `api/app/advisor/prompts/review.md` (new)
- `web/src/components/advisor/review-offer.tsx` (new)
- `api/evals/cases/review.yaml` (new)

## Notes
The review is what makes the advisor pass PRODUCT's monthly-use test on its own. If Wave 10's chat
turns out to be used weekly anyway, this is not needed.

## Done — 2026-09-29

The owner asked for it on 2026-09-29, before 107's production gates — like the rest of the
advisor it is built and tested switched off, and goes live with 107.

- **Migration 0012** gives `advisor_conversations` a `kind` (`chat` | `review`) and the
  `review_month` a review covers, checked together, with a partial unique index: one review of a
  month per person. That index is what makes the offer disappear once taken.
- `GET /advisor/status` carries `review_offer` — last month, and about what it costs on the
  configured model (a stated token estimate priced by `pricing.py`; null on the free local model)
  — while the advisor is on and no review of that month exists. `POST /advisor/conversations`
  with `kind: review` starts it, titled "August 2026 review"; a second is a 409.
- The review's fixed prompt is `advisor/prompts/review.md`: `findings_list`, `spend_compare`
  (the month against the one before), `cashflow_get`, `cards_value`, `networth_explain_change`
  and — for the runway section — `runway_get`; then **Spending**, **Subscriptions**, **Credits**,
  **Runway**, **Net worth**. It travels as this turn's context, never as the question, and goes
  out until a turn completes, so a failed first try is retried with it.
- The screen shows "Review August — … about $0.22" with Review and Not now. Not now is kept per
  month in localStorage (guarded; the offer just returns if it cannot be kept). Taking it passes
  "Review August." as the first question the way any conversation's first question travels.
- Evals: a `review` category with three cases, strict grounding, a `tools_all` check for the
  fixed lookups and an `expect_sections` check; the runner starts review cases the way the
  screen does. Fixed on the way: the retirement cases (118) were not rubric-graded — `ADVICE`
  is now `goal_aware` and `fire`.
- No email, no push, no scheduler.
