# 024 — Google Sheet history import
Status: in-progress
Wave: 2   Lane: B
Blocked by: 036, 011, 019
Read first: docs/SECURITY.md#handling-real-data-during-development

## Goal
A one-off script that reads an exported CSV of the existing spreadsheet's history and seeds
`balance_snapshots` with the net worth history that predates this app.

## Acceptance criteria
- [x] `api/scripts/import_sheet_history.py` reads from `data/` (gitignored)
- [x] Maps sheet columns to accounts via a committed mapping file containing **names only — no values**
- [x] Idempotent; safe to re-run as the mapping is corrected
- [x] Dry-run mode printing row counts and date ranges without writing
- [x] **Reconciliation report**: computed ownership-adjusted net worth per date vs. the sheet's own total, flagging mismatches
- [x] Writes through `services/balances.record_balance`, never directly to the table
- [x] Tests: unit for the column mapper; functional against a synthetic fixture with the same header shape, including a deliberate mismatch that the reconciliation report must flag

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

## Status — 2026-08-19: written and tested; running it is still blocked

The script, the mapping format and 40 tests exist. **Running it against the real export
remains blocked on 036 and 017**, which is what the blocker was actually protecting: the
danger is a complete financial history sitting behind no authentication and no proven
restore, not the existence of a script. Writing it against a synthetic fixture creates
no exposure.

**TOML, not the YAML the ticket named.** `tomllib` is stdlib on 3.12, so the mapping
format costs no dependency. TOML takes comments, which was the property that mattered —
a mapping nobody can annotate is a mapping nobody can correct.

**Reconciliation compares against the raw sum, not the ownership-adjusted figure**, and
this is the one design decision worth re-reading. A spreadsheet almost certainly does
not model fractional ownership, so comparing the adjusted number against the sheet's
total would flag every part-owned account as a mismatch and bury the real ones. The
adjusted figure is computed after writing — from `services/net_worth`, against the
database — and reported alongside, because it is what the app will actually show.

Decisions the tests pin down:

- **A blank cell is not zero.** It means the account did not exist yet. Recording zero
  would claim the balance *was* zero and drag net worth down for every date before the
  account opened.
- **Ambiguous dates are refused, not guessed.** `01/02/2026` is two dates, and choosing
  wrong shifts a year of history by eleven months, invisibly. The format must parse
  *every* row, not the first.
- **A number in the mapping file is rejected outright** — that file is committed and
  `data/` is not, so a value there is someone pasting real data into git.
- **Unmapped columns are named** in the dry run. An unmapped account is missing from
  every figure, and the only clue would be a total reading slightly low.

A non-breaking space got into a string literal again — the same invisible-character bug
as `csv_import.py`, caught by ruff this time rather than by reading. Stripping it is
correct (locales use it as a thousands separator, and spreadsheets export it verbatim);
it is now spelled `\u00a0` with the reason.

### Before running it for real

1. 036 and 017 done.
2. Export the sheet to `data/` and copy `api/config/sheet_mapping.example.toml` to
   `api/config/sheet_mapping.toml`.
3. Create the accounts first — this script records balances, it does not invent
   accounts, and it refuses a mapping naming one that does not exist.
4. Dry run until the reconciliation reports no mismatches:
   ```bash
   cd api && uv run python scripts/import_sheet_history.py ../data/history.csv
   ```
5. Then `--write`. Re-running after a correction is safe; every write is an upsert.
