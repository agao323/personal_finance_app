# 024 — Google Sheet history import
Status: todo
Wave: 2   Lane: B
Blocked by: 036, 011, 019
Read first: docs/SECURITY.md#handling-real-data-during-development

## Goal
A one-off script that reads an exported CSV of the existing spreadsheet's history and seeds
`balance_snapshots` with the net worth history that predates this app.

## Acceptance criteria
- [ ] `api/scripts/import_sheet_history.py` reads from `data/` (gitignored)
- [ ] Maps sheet columns to accounts via a committed mapping file containing **names only — no values**
- [ ] Idempotent; safe to re-run as the mapping is corrected
- [ ] Dry-run mode printing row counts and date ranges without writing
- [ ] **Reconciliation report**: computed ownership-adjusted net worth per date vs. the sheet's own total, flagging mismatches
- [ ] Writes through `services/balances.record_balance`, never directly to the table
- [ ] Tests: unit for the column mapper; functional against a synthetic fixture with the same header shape, including a deliberate mismatch that the reconciliation report must flag

## Files
- `api/scripts/import_sheet_history.py`
- `api/config/sheet_mapping.example.yml`
- `api/tests/test_sheet_import.py`

## Notes

**036 is a hard blocker, not an ordering preference.** This is the ticket that puts real
balances in the database, and until Cloudflare Access is in front of the origin the app is
publicly readable by anyone who knows the hostname. Importing before 036 means a window
where a complete financial history sits behind nothing.

Written against the **header shape**, not the values. The real export never leaves `data/` and
is never read into a session's context. See SECURITY#handling-real-data-during-development.

The reconciliation report is what proves the import is correct — do not skip it. This is also
where the schema gets reconciled against the real sheet; if a structural gap appears, add a
migration ticket rather than bending the import.

**Runs against a local database until ticket 017 is done.** No real data goes to production
before the restore has been tested.

This ticket depends only on snapshots and the accounts API — deliberately not on CSV import or
the rules engine, which concern a different table.
