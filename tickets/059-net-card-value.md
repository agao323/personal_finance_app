# 059 — Is this card paying for itself?
Status: todo
Wave: 7   Lane: W5
Blocked by: 053, 054
Read first: tickets/053-card-perks-schema-for-partial-use-and-fees.md

## Goal
Per card: the annual fee against the credit value actually realised this fee year.

## Why

The decision perk tracking serves is not "which credits exist" — it is **keep this card or
cancel it**. MaxRewards calls it net card value and it is the most useful idea in either
reference app. The data is already here once 053 lands: perk values, redemptions with
amounts, and a fee.

## Acceptance criteria
- [ ] Set a card's annual fee and renewal date
- [ ] Per card: fee, realised value in the current fee year, and the difference — stated
      plainly, no gauge or dial
- [ ] Realised value counts **redemption amounts**, falling back to face value when the
      amount is `NULL`. Never the sum of what is *available*, which would flatter every
      card
- [ ] The fee year runs from `fee_renews_on`, stepped annually — the same
      anchor-plus-cadence arithmetic as a perk, reusing `services/perks`
- [ ] A card with no fee set shows nothing. Absent is not zero
- [ ] Says nothing about whether to cancel. It reports two numbers and their difference;
      the judgement is the reader's, and a "cancel this card" badge would be advice this
      app is not positioned to give
- [ ] Tests: realised value with mixed partial and full redemptions; a fee year that
      straddles a calendar year; no fee set renders nothing

## Files
- `web/src/components/cards/net-value.tsx`
- `web/src/components/cards/net-value.test.tsx`
- `api/app/services/perks.py`

## Notes

Slots into the card row that 055 owns; this ticket owns only its own component, so the two
run in parallel.

**Not a recommendation engine.** No "you are losing money on this card" — a perk you chose
not to use is not the same as value destroyed, and the app does not know your reasons.
