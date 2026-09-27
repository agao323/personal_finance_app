# 073 — The calendar year replaces the fee year
Status: done
Wave: 7   Lane: —
Blocked by: none
Read first: docs/ARCHITECTURE.md#card_perks--perk_redemptions

## Goal
"Realised this fee year" becomes "Realised this year", measured on the calendar year and
computed by the same rule as the history panel below it, so the card screen stops carrying
two differently-computed answers to the same question. The fee's renewal date stays, demoted
from anchoring a window to telling you when you next get charged.

## Acceptance criteria
- [ ] `CardRead.realised_this_year_cents` replaces `realised_this_fee_year_cents`;
      `fee_year_start` is gone. `fee_renews_on` stays.
- [ ] Realised value is summed over redemptions whose `period_start` falls in the calendar
      year, and `_history` uses the same helper, so the two figures cannot disagree.
- [ ] The figure is present whenever the card has any recorded use, **independently of
      whether a fee or a renewal date is recorded**. Today it is `—` unless both exist.
- [ ] The Annual fee figure carries `Charged 1 March` beneath it when a renewal date is
      recorded; the realised figure carries no detail line at all.
- [ ] `fee_renews_on` is optional in the fee form: a fee with no date saves.
- [ ] `net-value.tsx` and its test are deleted. Nothing but its own test has imported it
      since 066 folded its figures into the summary.
- [ ] `make types` run and the regenerated `api-types.ts` committed.
- [ ] Tests: unit — the shared sum over a straddling period, counted once, in the year its
      period began. Functional — a credit used in January does not appear in the following
      year's figure; a card with a fee and no renewal date still reports realised value.
      Component — the fee date renders under the fee, nothing renders under realised.

## Files
- `api/app/routers/cards.py`
- `api/app/schemas/card_perk.py`
- `web/src/components/cards/card-detail.tsx`, `fee-form.tsx`
- `web/src/components/cards/net-value.tsx` (deleted), `net-value.test.tsx` (deleted)
- `api/tests/test_cards.py`, `web/src/components/cards/card-detail.test.tsx`

## Notes
The fee year served exactly one decision — keep this card or cancel it — and was bad at it.
`_realised` matched on period **overlap**, so on the second day of a new fee year a
calendar-year credit spent eleven months earlier still counted toward the fee just charged.
Overlap was the right fix when the window was the fee year (containment reported near-zero),
but it is the wrong shape for the question.

Containment is correct once the window is the calendar year, because it assigns each period
to exactly one year by its start, and it is what `_history` has always done. One helper, one
rule.

No migration: both columns stay. Only the response shape and the arithmetic change.

The per-perk `anchor_on` is untouched. That is what models a credit which genuinely does
reset on the cardmember year, and it keeps working.
