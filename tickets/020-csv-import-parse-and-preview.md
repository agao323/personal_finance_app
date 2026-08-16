# 020 — CSV import: parse and preview
Status: todo
Wave: 2   Lane: B
Blocked by: 012
Read first: docs/ARCHITECTURE.md#data-model

## Goal
Parse an uploaded CSV, detect its column mapping, normalise the sign convention, and show
exactly what a commit would change — without writing anything.

## Acceptance criteria
- [ ] `POST /import/csv/preview` returning parsed rows, detected column mapping, and a **diff** of what would be created vs updated — no writes
- [ ] **Sign normalisation** configurable per mapping: institutions disagree about whether a debit is negative
- [ ] Column mapping persisted per account in `import_mappings` for reuse
- [ ] Rejects files whose parsed amounts don't round-trip as `Decimal` at 2dp
- [ ] Rejects files with unparseable dates rather than guessing a format
- [ ] Tests: unit for the parser, the mapping detector, and sign normalisation; functional for preview against synthetic fixtures including a file using the opposite sign convention and a file with a malformed row

## Files
- `api/app/routers/import_csv.py`
- `api/app/services/csv_import.py`
- `api/tests/test_csv_import.py`
- `api/tests/fixtures/*.csv`

## Notes
Dry-run preview before commit is what makes this safe to iterate on with real exports. Build
it first, not as a later nicety — that's why it's a separate ticket from the commit path.

Fixtures are synthetic and generated. **Never copy a real export into `tests/fixtures/`**, even
with the numbers changed.
