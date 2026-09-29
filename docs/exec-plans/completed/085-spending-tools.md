# 085 — Spending tools: spend by category, transaction search, categories, rules
Status: done
Wave: 9   Lane: T
Touches: none
Blocked by: 082, 083
Read first: docs/ADVISOR.md#tool-catalog, docs/ADVISOR.md#arguments, docs/ARCHITECTURE.md#transfers

## Goal
The advisor can read spending the way the Spending screen does, and find individual transactions
when a question needs them — within strict bounds, counted against the turn's row budget.

## Acceptance criteria
- [x] `spend_by_category(period, group_by)` over `spend.spend_by_category`: buckets, prior
      period, uncategorised as its own bucket, `excluded_transfer_count`. Period ≤ 366 days.
- [x] `transactions_search` over `services/transactions.search`: date span ≤ 366 days, optional
      account, category, `uncategorised`, amount bounds, and `merchant_query` matching
      `^[A-Za-z0-9 &'.*#-]{2,40}$`; `page` 1–20, `page_size` ≤ 25; newest first; `total` and
      `has_more`. Rows count against the turn budget.
- [x] Row fields: id, date, amount, `merchant_text`, `description_text` (truncated to 80
      characters), category and kind, account id and name, transfer flag. No `external_id`.
- [x] `categories_list` (the two-level tree with kinds) and `rules_list` (order, `pattern_text`,
      match type, category).
- [x] None of these take a scope. A test asserts the rendered spend is identical for a `mine` and a
      `household` context.
- [x] Tests: hand-computed spend on fixtures including a refund, a transfer pair and an
      uncategorised row; search bounds and pagination; a merchant query containing `/` or `:`
      rejected; a planted injection string in a description comes back sanitised.

## Files
- `api/app/advisor/tools/spending.py` (new)
- `api/tests/test_advisor_tools_spending.py`

## Notes
`merchant_query` is the only free-text argument in the whole catalog. Keep it that way: 083's lint
test fails on a second one, and should.

Row-level data going to a hosted provider is item 2 of 122's working plan, confirmed at 107.
Development uses the local model over synthetic data, so building this tool commits nothing. If
the owner chooses aggregates only at 107, production disables `transactions_search` and the rest
stands.

## Done — 2026-09-27

- **Amount bounds are magnitudes.** `min_amount_cents` and `max_amount_cents` bound the size of the
  amount, ignoring its sign — "a charge of about $130" is a question about size, and outflows are
  stored negative. Implemented as `magnitude_min`/`magnitude_max` on
  `services/transactions.TransactionFilters`, so the screen could use them too.
- `merchant_query`'s pattern admits no `%` or `_`, so the `ILIKE` it becomes cannot carry a
  wildcard the model chose.
- `spend_by_category` names its comparison window and its dates: it is the service's equal-length
  prior period, and saying so stops a model presenting it as "last month".
- `categories_list` and `rules_list` read their tables directly. Each is an ordered `SELECT` with
  no rule in it, so there is no second implementation to drift.
- The spec's `description_text` truncation and the injection check are exercised through a memo
  that names `transactions_search` — withheld whole, and counted.
