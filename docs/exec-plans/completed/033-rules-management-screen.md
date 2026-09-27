# 033 — Rules management screen
Status: done
Wave: 2   Lane: C
Blocked by: 025
Integrates with: 022
Read first: docs/ARCHITECTURE.md#categories--categorization_rules

## Goal
The screen for editing the categorisation rule set — the thing that makes the spend numbers
trustworthy over time.

## Acceptance criteria
- [x] Rules listed in priority order, with drag or explicit reorder controls
- [x] Create, edit, delete a rule
- [x] **Match preview**: before saving, show which existing transactions the rule would match
- [x] Run-all-rules action with a result summary of how many transactions changed
- [x] A visible note that manual categorisations are never overwritten
- [x] Reachable from the uncategorised affordance in the spend view, prefilled with the merchant
- [x] Tests: component tests for reordering, the match preview, and the create-from-merchant prefill

## Files
- `web/src/app/(dashboard)/rules/page.tsx`
- `web/src/components/rules/rule-list.tsx`
- `web/src/components/rules/rule-form.tsx`

## Notes
Built against MSW mocks typed from `api-types.ts` — it does **not** wait for the
backend tickets above. Point it at the real endpoints once they land; ticket 038 verifies
the join.

PRODUCT.md commits to a user-editable rule set in v1. Editable by `curl` is not that.

The match preview is what makes rule-writing feel safe — writing a regex against your own
transaction history without seeing what it hits is how you end up mis-categorising two years of
data and not noticing.

## Done — 2026-08-18

The match preview needed `POST /rules/preview`, added in a re-freeze. It runs the
engine's own `compile_rules` / `first_match` over `subject_of`, not a `LIKE` query — an
approximation would agree with the engine right up until the pattern got subtle enough
to actually need checking, and `subject_of` falls back to the description when the
merchant column is empty, which a merchant-column `LIKE` would miss entirely.

The preview is explicit rather than live-as-you-type: firing on every keystroke would
run half-written regexes over the whole history repeatedly, and half-written regexes
are where the catastrophic ones come from. A pattern change clears the previous result
— a stale preview beside a changed pattern reads as confirmation of what is now on
screen.

`already_manual` is surfaced, so "matches 40" does not read as a promise to change 40.

**Reorder is explicit up/down buttons, not drag.** Drag needs a pointer path, a
keyboard alternative, and a live region to announce the result — three implementations
of one affordance for a list a dozen rows long that is reordered rarely. A move swaps
two priorities rather than renumbering the list, which would be one write per rule to
move one.

**The prefill affordance ended up on the transaction rows**, not on the spend
callout: the callout knows a total, and a rule needs a merchant. `TransactionTable`
grew an optional `offerRule` that puts a "rule" link on uncategorised rows, so the
spend view's uncategorised drill and the transactions screen both offer it exactly
where the gap is visible. That closes the loop the tickets describe — spending surfaces
it, transactions fixes it, a rule keeps it fixed.
