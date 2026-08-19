# 032 — CSV import wizard
Status: done
Wave: 2   Lane: C
Blocked by: 031
Integrates with: 020, 021
Read first: docs/ARCHITECTURE.md#data-model

## Goal
The CSV import flow: upload, map columns, preview the diff, commit.

## Acceptance criteria
- [x] Upload → column mapping → preview → commit, with back navigation between steps
- [x] Mapping prefilled from the account's saved `import_mappings` row
- [x] Sign convention selectable, with the effect visible in the preview
- [x] **Preview shows a diff of what will change**, not just row counts
- [x] Result summary: rows created, updated, skipped
- [x] Parse and validation errors surfaced per row, not as one opaque failure
- [x] Tests: component tests walking the full wizard against MSW, including a re-import that changes nothing and a file with malformed rows

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

## Done — 2026-08-18

Needed a re-freeze: `/import/csv/preview` took only a file and always ran the detected
or saved mapping, so "sign convention selectable, with the effect visible in the
preview" had nothing to call — a reader who spotted an inverted amount could only
correct it by committing and finding out. The route now takes an optional mapping as
JSON in the multipart form, and reports `mapping_source` so the wizard can say the
mapping was remembered rather than presenting a guess and a memory identically.

**Scope note on the diff.** The preview shows every row with the values it parsed —
date, merchant, amount — and what it would do with each, with problems and changes
sorted to the top. That is what distinguishes a right mapping from a wrong one, which
is the ticket's stated reason for wanting a diff. It is not a before/after comparison
on `update` rows: `PreviewRow` carries the incoming values only, and the existing row
it would overwrite is not in the response. Adding old values would be another contract
change; worth doing if updates ever become common, but the import owns only four
fields and the incoming view is what catches a mis-mapped column.

Two environment findings:

- **`apiFetch` gained a `formData` escape hatch.** A multipart operation is generated
  as an object of field names, not something `JSON.stringify` could produce, so the
  typed `body` cannot express it. Content-type is left unset so the browser adds its
  own boundary.
- **jsdom's `File` is not undici's.** MSW reads request bodies in Node with undici's
  multipart parser, which brand-checks against its own `File` and rejects jsdom's — so
  a real upload failed in tests while working in a browser. `vitest.setup.ts` now
  restores Node's `File` and `Blob`.
