# 015 — Spend by category endpoint
Status: done
Wave: 2   Lane: A
Blocked by: 012
Read first: docs/ARCHITECTURE.md#transfers, docs/ARCHITECTURE.md#data-model

## Goal
Spend rollups by category for a period, powering the MTD and YTD dashboard views.

## Acceptance criteria
- [x] `GET /spend?from=&to=&group_by=category|parent_category`
- [x] **Excludes `categories.kind = 'transfer'`** and excludes `kind = 'income'`
- [x] Returns uncategorised as an explicit bucket, not silently dropped
- [x] Comparison to the prior equivalent period
- [x] Rollups are **per account, never fractionally attributed by ownership** — a $60 charge on a jointly-owned card is $60 of spend
- [x] Tests: unit for the rollup with hand-computed totals; functional covering a transfer pair that must not appear, an uncategorised row that must appear, and the prior-period comparison across a month boundary

## Files
- `api/app/routers/spend.py`
- `api/app/services/spend.py`
- `api/tests/test_api_spend.py`

## Notes
Transfer exclusion is the thing that makes these numbers believable. A transfer from checking
to brokerage is not spending; if it shows up as spending the whole dashboard loses credibility.
The mechanism is `categories.kind`, created in 009 — see ARCHITECTURE#transfers.

Not attributing spend by ownership is deliberate and worth an inline comment: splitting a
grocery charge 50/50 has no correct answer and isn't what the number is for.
