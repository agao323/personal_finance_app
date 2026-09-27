# 062 — Set a card's annual fee
Status: done
Wave: 7   Lane: —
Blocked by: none
Read first: docs/exec-plans/completed/059-net-card-value.md

## Goal
The column exists and 059 renders the figures; nothing can populate it.

## Acceptance criteria
- [x] Set and clear `annual_fee` and `fee_renews_on` from the card row
- [x] `PATCH /accounts/{id}` accepts both. The account schema currently has neither
- [x] **Clearing means null, not zero.** A card with no fee shows nothing; a card with a
      $0 fee is a different claim and a rarer one
- [x] The renewal date explains itself — it is the anniversary the fee is charged on, and
      it sets the fee year 059 measures against
- [x] Tests: setting both, clearing to null, and that a null fee renders no net-value panel

## Files
- `api/app/schemas/account.py`, `api/app/routers/accounts.py`
- `web/src/components/cards/fee-form.tsx`

## Done — 2026-09-26

`annual_fee_cents` is popped from the payload and converted once, so no path assigns an
integer number of cents to a money column — the same shape of bug I shipped and fixed in
054's `update_perk`.

Clearing writes null, and there is a test for it. A card with no fee shows no net-value
panel at all; a $0 fee is a different claim, and collapsing them would make "not filled in"
indistinguishable from "free".
