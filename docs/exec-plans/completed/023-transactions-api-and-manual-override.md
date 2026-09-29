# 023 — Transactions API and manual category override
Status: done
Wave: 2   Lane: B
Blocked by: 022
Read first: docs/ARCHITECTURE.md#data-model, docs/ARCHITECTURE.md#transfers

## Goal
The transactions read API and the write path that sets `category_source='manual'` — the
capability the entire categorisation design exists to protect.

## Acceptance criteria
- [x] `GET /transactions` with filters: date range, account, category, uncategorised-only, and text search over merchant and description
- [x] Cursor or offset pagination, with a documented choice
- [x] `PATCH /transactions/{id}` setting `category_id` and `category_source='manual'`
- [x] `PATCH /transactions/{id}` marking or unmarking a transfer, writing `transfer_group_id`
- [x] `POST /transactions/bulk-categorise` applying a category to a filtered set, as manual
- [x] Tests: unit for the filter query builder across every filter combination; functional asserting a manual override **survives a subsequent `POST /rules/apply`**, and that bulk-categorise writes `manual` for every affected row

## Files
- `api/app/routers/transactions.py`
- `api/app/schemas/transaction.py`
- `api/tests/test_api_transactions.py`

## Notes
This is the write path the whole `category_source` design exists for. Without it, `'manual'` is
an enum value nothing ever sets and the protection in 022 guards nothing.

The uncategorised-only filter is what makes the feedback loop work: the spend view surfaces
uncategorised spend, this endpoint is how it gets fixed, and a rule gets written so it stays
fixed.
