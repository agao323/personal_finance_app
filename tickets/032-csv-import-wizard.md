# 032 — CSV import wizard
Status: todo
Wave: 2   Lane: C
Blocked by: 031
Integrates with: 020, 021
Read first: docs/ARCHITECTURE.md#data-model

## Goal
The CSV import flow: upload, map columns, preview the diff, commit.

## Acceptance criteria
- [ ] Upload → column mapping → preview → commit, with back navigation between steps
- [ ] Mapping prefilled from the account's saved `import_mappings` row
- [ ] Sign convention selectable, with the effect visible in the preview
- [ ] **Preview shows a diff of what will change**, not just row counts
- [ ] Result summary: rows created, updated, skipped
- [ ] Parse and validation errors surfaced per row, not as one opaque failure
- [ ] Tests: component tests walking the full wizard against MSW, including a re-import that changes nothing and a file with malformed rows

## Files
- `web/src/app/(dashboard)/import/page.tsx`
- `web/src/components/import/csv-wizard.tsx`
- `web/src/components/import/column-mapper.tsx`
- `web/src/components/import/import-preview.tsx`

## Notes
Built against MSW mocks typed from `api-types.ts` — it does **not** wait for the
backend tickets above. Point it at the real endpoints once they land; ticket 038 verifies
the join.

The preview step is the safety net for importing real exports. **Show diffs, not just counts** —
"312 rows updated" tells you nothing about whether the mapping is right; a diff does.

Split out from the manual entry forms deliberately: a four-step wizard plus four forms is two
sessions of work, not one.
