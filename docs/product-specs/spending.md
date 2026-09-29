# Spending

Where the money went, by category, for a period — trustworthy enough to act on.

## What you can do

- Choose a period: **month to date, year to date**, or a custom range.
- See a **category breakdown chart and a sortable table**, with each category compared to the
  prior period of equal length.
- **Drill down** from a parent category to its children to the transactions themselves.
- See **uncategorised spend prominently**, with a link to the transactions screen filtered to
  uncategorised rows, where each one offers "rule" to create a rule prefilled with its
  merchant.

## Rules and edge cases

- **Transfers and income never count as spend** — the mechanism is `categories.kind`, and a
  transfer pair must never appear ([transfers-and-categories](../design-docs/transfers-and-categories.md)).
  The response reports how much was excluded as transfers.
- **Spend is never split by ownership.** A $60 charge on a jointly owned card is $60 of spend.
- **Uncategorised is its own bucket**, never dropped — it is the feedback loop that keeps the
  rules current.
- **A refund reduces spend** in its category.
- **The prior period is equal length**, not "the previous calendar month", so a comparison
  across a month boundary is like for like. Range boundaries are inclusive.
- Buckets are ordered largest first. Leaf buckets carry their `parent_id` so the screen can
  build the tree without re-implementing the server's rules.
- The breadcrumb tracks the breakdown, not the selection — a number under a label reads as
  that label's number.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/spend?from=&to=&group_by=category\|parent_category` | Defaults to month to date. Integer cents |
| GET | `/transactions?category_id=…` | The drill-down rows |

## Screens and code

`web/src/app/(dashboard)/spending/page.tsx` — `components/charts/category-breakdown.tsx`,
`period-selector.tsx`, `transaction-table.tsx`. API: `services/spend.py`, `routers/spend.py`.

## Built by

015 (the endpoint), 028 (the screen, and the `parent_id` re-freeze), 030 (the uncategorised
link goes to the transactions screen), 033 (the rule prefill on rows).
