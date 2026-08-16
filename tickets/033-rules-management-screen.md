# 033 — Rules management screen
Status: todo
Wave: 2   Lane: C
Blocked by: 025
Integrates with: 022
Read first: docs/ARCHITECTURE.md#categories--categorization_rules

## Goal
The screen for editing the categorisation rule set — the thing that makes the spend numbers
trustworthy over time.

## Acceptance criteria
- [ ] Rules listed in priority order, with drag or explicit reorder controls
- [ ] Create, edit, delete a rule
- [ ] **Match preview**: before saving, show which existing transactions the rule would match
- [ ] Run-all-rules action with a result summary of how many transactions changed
- [ ] A visible note that manual categorisations are never overwritten
- [ ] Reachable from the uncategorised affordance in the spend view, prefilled with the merchant
- [ ] Tests: component tests for reordering, the match preview, and the create-from-merchant prefill

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
