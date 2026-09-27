# 054 — Card perks API: editing, deleting, history, urgency
Status: done
Wave: 7   Lane: —
Blocked by: 053
Read first: docs/exec-plans/completed/050-card-perks-api.md

## Goal
Every endpoint the rebuilt page needs. After this, tickets 055–059 are frontend-only and
can run in parallel.

## Acceptance criteria
- [x] `DELETE /perks/{perk_id}` — **refused with 409 when the perk has any redemption.**
      Deleting one that was genuinely used would erase history; retiring
      (`is_active = false`, already in 050) is the answer there. Delete exists for the
      perk you added by mistake, and the response says which case you hit
- [x] `GET /perks/{perk_id}/history` — every redemption, newest first, with the period it
      belongs to, the amount (face value when `NULL`), and the note. Covers **first
      redemption to most recent**, with an optional `from`/`to` window
- [x] `GET /cards/history` — the same across every card, for the whole-wallet view.
      Optional window; **no default cut-off**, because "show me everything" is the
      request that was actually made
- [x] `POST /perks/{perk_id}/redemptions` accepts an optional `amount_cents`, and still
      accepts `on` for backfilling a past period. Marking twice stays idempotent; a
      second mark with a different amount **updates** it rather than erroring
- [x] `GET /perks/upcoming` gains `is_urgent` per perk from `services/perks.is_urgent`,
      and keeps `within_days` as a caller-supplied horizon. Default raised to **90** so
      an annual credit is visible without asking
- [x] `GET /cards` reports, per card: perk count, available value this period, and — when
      `annual_fee` is set — fee and value realised in the current fee year
- [x] `PATCH /accounts/{id}` already renames a card; assert it in a test here so the
      rebuild does not discover it is missing
- [x] Update the endpoint table in `docs/ARCHITECTURE.md` — the contract test parses it
- [x] Re-freeze the contract: `make types`, commit `api-types.ts`
- [x] Tests: the 409 on deleting a used perk and the 204 on an unused one; history
      ordering and windowing; a partial amount round-tripping as cents; re-marking with a
      new amount; urgency true/false at each cadence boundary; totals in `GET /cards`

## Files
- `api/app/routers/cards.py`
- `api/app/schemas/card_perk.py`
- `api/tests/test_cards.py`
- `docs/ARCHITECTURE.md`

## Notes

**History comes from stored `period_start`**, never recomputed from a cadence that may
have been edited since — 049 made that choice and this ticket depends on it.

Every date is still a parameter. Nothing in this area reads the clock.

## Done — 2026-09-26

**One real design error, caught by a test rather than by review.** `_realised` first filtered
redemptions on `period_start >= fee_year_start`, which reads as obviously correct and is
badly wrong for the commonest real case: an Amex fee renews on your card anniversary while
its credits reset on the calendar year, so a credit's period almost always *starts before*
the fee year it is being counted against. That version reported nearly zero realised for
most of every fee year. It now tests **overlap** — `period.end > since and period.start <=
until` — and the cost is stated in the code: a period straddling two fee years counts in
both, which is defensible because the credit genuinely was available in both, and far less
wrong than reporting nothing.

**Two of my own edits silently did nothing** and one test I wrote was arithmetically wrong.
The `mark_used` replacement targeted a multi-line form that `ruff format` had already
collapsed to one line, so `str.replace` matched nothing — and I had not asserted a match
count on that one, unlike the others. Then the fix-up for it missed for the same reason. The
lesson is narrow and worth keeping: **assert the replacement count every time**, including
on the edit that looks too simple to need it. The urgency test asserted a monthly credit was
urgent at 10 days remaining when its threshold is 7; the test was wrong, not the code, and it
now checks three dates across two cadences instead of one.

**Delete versus retire** are two actions that look alike, and the 409 names the alternative
rather than just refusing. Delete is for the perk added by mistake; retire keeps the
redemptions that record what was actually used.

**History has no default window**, which was the explicit request. `missed_periods` walks
each perk's periods rather than inferring a count, because a cadence determines how many
periods a span even contains — and only periods that have *ended* can be called missed, since
the current one is still spendable.

Contract re-freeze is additive: +263 lines. Guards 19, API 509, web 418.
