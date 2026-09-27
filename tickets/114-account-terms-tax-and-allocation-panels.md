# 114 — Account detail: terms, tax treatment and allocation, where the account is
Status: todo — order provisional
Wave: 12   Lane: W
Touches: none
Blocked by: 112, 113
Read first: docs/ADVISOR.md#data-model-additions

## Goal
The facts Wave 12 adds are entered and read on the account they describe — not on a separate
settings page.

## Acceptance criteria
- [ ] On a liability's detail page, a **Terms** panel: APR, minimum payment, credit limit (cards),
      term or maturity, promo rate and end date, and "checked on" with a stale badge past a year.
- [ ] On every account, the tax treatment in the account form, with help text for the Roth-401k
      split.
- [ ] On investment accounts, an **Allocation** panel: current percentages by class, "unknown" when
      none are set, presets ("target-date 2055 ≈ 90/10", "100% cash"), and the history of changes.
      The form will not save unless the classes total 100.
- [ ] Each edit control sits in the panel it edits. Saving a panel updates that panel only.
- [ ] Tests (MSW): terms staleness; allocation presets fill the form; a 99.99% total cannot save; a
      save leaves the other panels as they were.

## Files
- `web/src/components/accounts/terms-panel.tsx` (new)
- `web/src/components/accounts/allocation-panel.tsx` (new)
- `web/src/components/forms/account-form.tsx`
- `web/src/app/(dashboard)/accounts/[id]/page.tsx`
- `web/src/components/accounts/allocation-panel.test.tsx`
