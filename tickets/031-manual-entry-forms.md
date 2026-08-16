# 031 — Manual entry forms
Status: todo
Wave: 2   Lane: C
Blocked by: 029
Integrates with: 019
Read first: docs/ARCHITECTURE.md#users-and-ownership

## Goal
The forms for getting data in by hand: create/edit an account, record a balance, set an
ownership stake, close an account.

## Acceptance criteria
- [ ] Account create/edit form with validation mirroring the API's
- [ ] Balance entry with a date picker defaulting to today
- [ ] Ownership stake form that **explains the effective-date behaviour in plain language** and previews the resulting stake history
- [ ] Close-account action setting `closed_at`, with a confirmation explaining it removes the account from future net worth
- [ ] Money inputs accept dollars and submit integer cents
- [ ] Tests: component tests for each form's validation paths, the stake form's date handling, and the dollars-to-cents conversion including a half-cent input

## Files
- `web/src/app/(dashboard)/accounts/new/page.tsx`
- `web/src/components/forms/account-form.tsx`
- `web/src/components/forms/balance-form.tsx`
- `web/src/components/forms/stake-form.tsx`

## Notes
Built against MSW mocks typed from `api-types.ts` — it does **not** wait for the
backend tickets above. Point it at the real endpoints once they land; ticket 038 verifies
the join.

The stake form is the one that needs real copy, not a bare percentage input. "Changing this
closes the current stake on <date> and opens a new one — your past net worth won't change" is
the sentence that makes the effective-dating comprehensible instead of confusing.
