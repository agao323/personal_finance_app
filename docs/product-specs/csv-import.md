# CSV import

The way transactions get in for any institution, including the ones no aggregator covers.

## What you can do

A four-step wizard at `/import`, with back navigation between steps:

1. **Upload** a CSV and choose the account it belongs to.
2. **Map columns** — prefilled from the account's saved mapping if there is one, otherwise
   detected. The screen says which: remembered, detected, or supplied by you. Choose the
   sign convention and see its effect.
3. **Preview** every row with the values parsed from it and what would happen — create,
   update or skip — with problems and changes sorted to the top, and errors attached to the
   row that caused them.
4. **Commit**, and see rows created, updated and skipped. Optionally save the mapping so the
   next import of the same export is one click.

## Rules and edge cases

- **Re-importing the same file changes nothing.** Importing a superset adds only the new
  rows. Ingestion is upsert, never insert
  ([transactions-and-ingestion](../design-docs/transactions-and-ingestion.md)).
- **Two identical rows are two transactions** — same day, shop and amount get distinct ids
  through an occurrence index. A source-provided transaction id is used as the key when the
  file has one.
- **The preview is the plan the commit executes** — not a second implementation.
- **Signs are configuration, not inference.** Storage is always outflows negative; an export
  that writes a $12 coffee as `12.00` is imported with the invert option, remembered per
  account.
- **An amount that doesn't round-trip at 2dp is rejected**, never rounded, and never parsed
  through float. **An unparseable date is rejected**, never guessed.
- The preview shows incoming values, not the old values an update would overwrite (a
  deliberate scope cut in 032).
- Fixtures are synthetic. Never copy a real export into `tests/fixtures/`, even with the
  numbers changed.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/import/csv/preview` | Multipart: `account_id`, `file`, optional `mapping` (JSON). Writes nothing |
| POST | `/import/csv/commit` | JSON: `account_id`, `mapping`, `content` (the raw CSV), optional `save_mapping_as`. Re-plans with the same planner and executes it |

## Screens and code

`web/src/app/(dashboard)/import/page.tsx` — `components/import/{csv-wizard,column-mapper,import-preview}.tsx`.
The upload uses `apiFetch`'s `formData` escape hatch. API: `services/csv_import.py`,
`routers/import_csv.py`, `models/system.py` (`ImportMapping`).

## Built by

020 (parse and preview), 021 (commit and upsert), 032 (the wizard, and the mapping-override
re-freeze).
