# 113 — Tax treatment per account, and account-level allocation
Status: todo — order provisional
Wave: 12   Lane: —
Touches: **migration** (after 112) · **contract** (`AccountRead` gains `tax_treatment`)
Blocked by: 112
Read first: docs/ADVISOR.md#tax-treatment-wave-12-migration-in-113, docs/ADVISOR.md#account-level-allocation-not-holdings, docs/adr/0013-allocation-is-recorded-per-account-not-per-holding.md

## Goal
Each account says how it is taxed and, for investment accounts, what it holds by asset class — the
two facts PRODUCT's FIRE bar needs that the app does not have.

## Acceptance criteria
- [ ] `accounts.tax_treatment` enum, backfilled from `subtype` in the migration as ADVISOR.md lists,
      editable through `PATCH /accounts/{account_id}`.
- [ ] `account_allocations`, effective-dated with half-open ranges exactly as `ownership_stakes` is;
      the invariant — rows in force on any date sum to exactly 100 per account — enforced in the
      service and tested across a transition, as the stake invariant is.
- [ ] `GET POST /accounts/{account_id}/allocations` — list, and set a new allocation effective from
      a date, closing the previous one atomically.
- [ ] Cash, property and vehicle accounts report a **derived** allocation from `subtype`; an
      investment account with no rows reports **unknown**.
- [ ] Revision 0011, hand-reviewed; `account_allocations` in `EXPORTED` and `ExportRead`;
      `make types` run.
- [ ] Tests: the backfill for every subtype; a transition closes the old rows and opens new ones
      with no gap or overlap; a set that sums to 99.99 is refused.

## Files
- `api/app/models/account.py`, `api/alembic/versions/0011_tax_and_allocation.py` (new)
- `api/app/services/allocations.py` (new)
- `api/app/schemas/account.py`, `api/app/routers/accounts.py`
- `api/app/schemas/export.py`, `api/app/routers/export.py`
- `api/tests/test_allocations.py`

## Notes
More than five files, but four of them are one-line additions to schemas and the export. If it
grows beyond that, split tax treatment from allocation.

A 401k with a Roth portion is recorded as two accounts. Say so in the account form's help text,
because the alternative — a split tax treatment on one account — is a second allocation-like table
nobody needs yet.
