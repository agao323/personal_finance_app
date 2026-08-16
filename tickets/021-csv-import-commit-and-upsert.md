# 021 — CSV import: commit and upsert
Status: todo
Wave: 2   Lane: B
Blocked by: 020
Read first: docs/ARCHITECTURE.md#data-model

## Goal
The write half of CSV import: idempotent upsert with a deterministic identity for rows the
source doesn't identify.

## Acceptance criteria
- [ ] `POST /import/csv/commit` performing the upsert
- [ ] Deterministic `external_id` = hash of row content **plus an occurrence index** within (`account_id`, `posted_at`, `amount`, `merchant`)
- [ ] Idempotent: re-importing the same file changes nothing
- [ ] Re-importing a superset file adds only the new rows
- [ ] Result summary: rows created, updated, skipped
- [ ] Balance rows in an import route through `services/balances.record_balance`
- [ ] Tests: unit for `external_id` generation, specifically **two genuinely identical rows on the same day** (two coffees, same shop, same amount); functional asserting a double import is a no-op and a superset import adds exactly the delta

## Files
- `api/app/routers/import_csv.py`
- `api/app/services/csv_import.py`
- `api/tests/test_csv_import.py`

## Notes
Upsert, never insert. Duplicate transactions after a re-import are the most common bug in this
category of app.

The occurrence index is the non-obvious part: a plain content hash silently collapses two real
identical transactions into one, and you find out months later when a category total is quietly
low. See ARCHITECTURE#transactions.
