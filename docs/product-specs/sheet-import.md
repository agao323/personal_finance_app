# Google Sheet history import

A one-off script that seeds `balance_snapshots` with the net worth history the spreadsheet
holds from before this app existed. Without it, "net worth over time" starts on the day the
app was deployed. **Written and tested; not yet run against the real export.**

## What you can do

1. Export the sheet to `data/` — gitignored, never read into a session.
2. Copy `api/config/sheet_mapping.example.toml` to `api/config/sheet_mapping.toml` (also
   gitignored) and map each column header to an account **by name**.
3. Create the accounts first; the script records balances, it does not invent accounts.
4. **Dry run** until the reconciliation report shows no mismatches:
   `cd api && uv run python scripts/import_sheet_history.py ../data/history.csv`
5. Run again with `--write`. Re-running after a correction is safe.

The owner runs this, not an agent — see [going-live §D](../runbooks/going-live.md#d--ticket-024--import-your-spreadsheet-history).

## Rules and edge cases

- **Gated.** It puts real balances in production, so it waits for Cloudflare Access (036,
  done) and for a restore drill against a production export (TD-003). Until then it runs
  against a local database only.
- **The mapping file holds names only.** A number in it is rejected outright — that file is
  committed and `data/` is not.
- **A blank cell is not zero**; it means the account did not exist yet.
- **Ambiguous dates are refused**, and the date format must parse every row, not the first.
- **Reconciliation compares the raw sum** against the sheet's own total, because the sheet
  almost certainly does not model fractional ownership; the ownership-adjusted figure is
  reported alongside. Unmapped columns are named in the dry run.
- Writes go through `services/balances.record_balance`, like every balance write, so every
  write is an upsert.
- Where the sheet reveals a structural gap in the schema, that is a migration plan, not a
  bent import.

## Endpoints

None. `api/scripts/import_sheet_history.py`; config `api/config/sheet_mapping.example.toml`
(TOML rather than the YAML the ticket named: stdlib on 3.12, and it takes comments).

## Built by

024 (in progress: the script and its 40 tests are done; the real run is TD-004). Design:
[transactions-and-ingestion](../design-docs/transactions-and-ingestion.md#google-sheet-history-code-touches-the-data).
