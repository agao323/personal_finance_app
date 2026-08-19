# 031 — Manual entry forms
Status: done
Wave: 2   Lane: C
Blocked by: 029
Integrates with: 019
Read first: docs/ARCHITECTURE.md#users-and-ownership

## Goal
The forms for getting data in by hand: create/edit an account, record a balance, set an
ownership stake, close an account.

## Acceptance criteria
- [x] Account create/edit form with validation mirroring the API's
- [x] Balance entry with a date picker defaulting to today
- [x] Ownership stake form that **explains the effective-date behaviour in plain language** and previews the resulting stake history
- [x] Close-account action setting `closed_at`, with a confirmation explaining it removes the account from future net worth
- [x] Money inputs accept dollars and submit integer cents
- [x] Tests: component tests for each form's validation paths, the stake form's date handling, and the dollars-to-cents conversion including a half-cent input

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

## Done — 2026-08-18

`parseDollarsToCents` splits the string rather than multiplying. `parseFloat("12.34") * 100`
is `1233.9999999999998`, so every money input in the app would have been a cent light
on some fraction of entries, unpredictably. A half cent rounds away from zero to match
`ROUND_HALF_UP` in `services/ownership.py` — rounding differently in the browser than
the server does is how a total disagrees with the row that produced it. Same reasoning
for `percentToBps`: `33.33 * 100` is `3332.9999999999995`.

Money inputs are `type="text"`, not `type="number"`. A number input silently discards
what it cannot parse, so a typo becomes an empty field with no message.

The stake form's preview is the ticket's real requirement. The sentence names the
dates, and the table underneath shows the resulting history with the new row marked —
the reader can check the claim "your past net worth will not change" against rows that
end before the change instead of taking it on trust. `previewStakes` mirrors
`transition_stake` in `services/ownership.py`, including the case where a change dated
at or before a stake's own start replaces it rather than closing it into a zero-length
range.

Closing an account states what it does *and does not* do — the balance stops counting,
the history and transactions stay, nothing is deleted. A confirmation that only asked
"are you sure?" would leave the reader guessing which of those they were agreeing to.

**Repointed 029's stale-balance prompt** at the balance form on the same page, rather
than at `/import` where it was parked.

Two things the ticket did not anticipate:

- **`components/forms/fields.tsx`** — the field wrapper and money input, so error
  messages get `aria-describedby` and `aria-invalid` once rather than four times.
- **Whose stake is changing** is a picker, because there is no `/users` endpoint: the
  owners the UI can name are the ones already on the account. Ticket 034 brings a real
  session and this becomes "you".
