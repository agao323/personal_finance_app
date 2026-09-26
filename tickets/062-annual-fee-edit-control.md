# 062 — Set a card's annual fee
Status: todo
Wave: 7   Lane: —
Blocked by: none
Read first: tickets/059-net-card-value.md

## Goal
The column exists and 059 renders the figures; nothing can populate it.

## Acceptance criteria
- [ ] Set and clear `annual_fee` and `fee_renews_on` from the card row
- [ ] `PATCH /accounts/{id}` accepts both. The account schema currently has neither
- [ ] **Clearing means null, not zero.** A card with no fee shows nothing; a card with a
      $0 fee is a different claim and a rarer one
- [ ] The renewal date explains itself — it is the anniversary the fee is charged on, and
      it sets the fee year 059 measures against
- [ ] Tests: setting both, clearing to null, and that a null fee renders no net-value panel

## Files
- `api/app/schemas/account.py`, `api/app/routers/accounts.py`
- `web/src/components/cards/fee-form.tsx`
