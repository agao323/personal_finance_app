# Transactions and ingestion

How money movements and balances get into the database without duplicates, without
guessing, and without anyone reading real values into a session. Code:
`api/app/services/csv_import.py`, `api/app/routers/import_csv.py`,
`api/scripts/import_sheet_history.py`, `api/app/services/balances.py`.

## `transactions`

```
external_id (nullable, unique per account), account_id, posted_at, amount, merchant,
description, category_id, category_source, transfer_group_id (nullable)
```

`external_id` + account is the idempotency key — a partial unique index, so rows without
an id (manual entries) are unconstrained and any source-provided id is unique within its
account. **Ingestion is upsert, never insert.** Duplicate transactions after a re-sync are
the single most common bug class in this category of app; it was designed out on day one
rather than debugged later.

Where the source provides no id, `external_id` is derived deterministically
(`csv_import.derive_external_id`) from the row's content **plus an occurrence index**
within `(account, posted_at, amount, merchant)`. The index matters: two coffees at the same
shop on the same day for the same amount are two real transactions that a naive content
hash would silently collapse into one — and nothing would fail; a category total would just
be quietly low. Derived ids are prefixed `csv:` so they are never mistaken for one the bank
issued. Reordering rows *within* one such group would shuffle the ids; no content-derived
identity can avoid that, and the fix when it matters is an export that carries a real id.

**Sign convention: outflows are negative, inflows positive.** Institutions disagree, and
there is no way to detect which from the file alone — a card export of a month with no
refunds is all one sign either way — so it is configuration, not inference:
`ColumnMapping.invert_amount`, persisted per account.

`category_source` (`import | rule | manual`) records where a category came from, so
re-running rules never clobbers a human decision. See
[transfers-and-categories.md](transfers-and-categories.md).

`transfer_group_id` links the two sides of a matched transfer. Set by hand in v1.

## `import_mappings`

Per-account CSV column mapping and sign convention, stored as a named layout, so a
recurring import from the same institution is one click. Institutions each export a
different shape and never change it.

## CSV import: the preview is the product

Importing a real export is the one moment this app touches data it cannot regenerate. So
the parse produces a **plan** — a per-row create / update / skip, with errors attached to
the row that caused them — and **the commit route executes that same plan**. What the user
approves in the preview is literally what is written, rather than a second implementation
that agrees with the first until it doesn't.

- **Amounts never pass through `float`.** A row whose amount does not round-trip at 2dp is
  rejected rather than rounded: silently turning `12.345` into `12.35` is a cent nobody
  will find again.
- **Unparseable dates are refused, not guessed.**
- **The mapping can be overridden in the preview** (ticket 032), and the response says
  whether the mapping was detected, remembered, or supplied — a guess and a memory should
  not look identical.
- **Balance rows in an import route through `record_balance`**, like every other balance
  write.

The preview shows every row's parsed values and action, problems first. It does not show
the *old* values an `update` would overwrite — that would be another contract change,
deferred until updates are common (ticket 032's scope note).

User-facing behaviour: [product-specs/csv-import.md](../product-specs/csv-import.md).

## Google Sheet history: code touches the data

`api/scripts/import_sheet_history.py` seeds `balance_snapshots` with the history that
predates the app. It is the ticket that puts real values in the database, so it was
written against the **header shape** and synthetic fixtures, and the real export never
leaves `data/` ([SECURITY.md](../SECURITY.md#handling-real-data-during-development)).

- The column → account mapping is a committed TOML file of **names only**; a number in it
  is rejected outright, because that file is committed and `data/` is not.
- **A blank cell is not zero** — it means the account did not exist yet.
- **Ambiguous dates are refused.** `01/02/2026` is two dates; guessing wrong shifts a year
  of history by eleven months, invisibly. The format must parse every row, not the first.
- **Dry run by default**, with a **reconciliation report** against the sheet's own total.
  It compares the *raw* sum, because a spreadsheet almost certainly does not model
  fractional ownership — comparing the adjusted figure would flag every part-owned
  account and bury the real mismatches. The adjusted figure is reported alongside.
- Unmapped columns are named, because an unmapped account is missing from every figure
  and the only clue would be a total reading slightly low.
- Writes go through `record_balance`, so re-running after a correction is safe.

Running it for real is gated — see [product-specs/sheet-import.md](../product-specs/sheet-import.md).

## Connectors, later

SimpleFIN is planned ([075](../exec-plans/active/075-simplefin-connector.md)). The
properties above are what make a sloppy sync window safe: a 5-day overlap re-fetches rows
that already exist, and the upsert makes that free. The `external_id` index does **not**
protect across sources — the same transaction arriving by CSV and by connector has two
ids — which is one of 075's open decisions. See [account-sources.md](account-sources.md).
