# 082 — Card, perk and transaction reads move from routers into services
Status: done
Wave: 9   Lane: —
Touches: none (no contract change, no migration)
Blocked by: none
Read first: docs/ADVISOR.md#principles, docs/adr/0006-contract-changes-during-wave-2.md

## Goal
The read logic that lives inline in routers moves into services, so an advisor tool and a screen
call **one** implementation. Nothing a user sees changes.

## Acceptance criteria
- [x] `services/cards.py` holds the card list with perks and current periods, upcoming perks, the
      history walk including `missed_periods`, `_realised_value` and realised-this-year — all
      moved from `routers/cards.py`, which becomes a thin mapper to schemas.
- [x] `services/transactions.py` holds `search(session, filters, limit, offset)` returning rows and
      a total — moved from `routers/transactions.list_transactions`.
- [x] `services/spend.py` exposes `expense_rows(session, start, end)` and
      `spend_totals(session, start, end, by_parent)` — today's private `_spend_query` and `_totals`
      — so analyses reuse the transfer, refund, income and uncategorised rules instead of
      restating them.
- [x] Behaviour identical: every existing test passes **unchanged**, and `make types` produces no
      diff.
- [x] Tests: unit tests for each newly public function on synthetic fixtures with hand-computed
      values, including a missed period and a partial redemption.

## Files
- `api/app/services/cards.py` (new), `api/app/routers/cards.py`
- `api/app/services/transactions.py` (new), `api/app/routers/transactions.py`
- `api/app/services/spend.py`

## Notes
This is ADR 0006's lesson applied before rather than after: every workaround there was a second
implementation of one rule, and the two disagreed the first time either changed. A tool that
re-queried perks its own way would eventually tell the chat something the cards screen does not.

Pure move. If a behaviour looks wrong while moving it, add a ticket; do not fix it here, or the
"tests unchanged" criterion stops meaning anything.

## Done — 2026-09-27

Services return plain dataclasses with `Decimal` money (`PerkView`, `CardView`, `History`,
`Upcoming`, `SearchResult`); routers map them to the unchanged wire schemas. All 565 existing tests
passed before any new one was written, and `make types` produced no diff.

- `perk_periods` stays in the router. It is the period grid's own read, and no tool needs it.
- `spend.expense_query` is public too, alongside `expense_rows` and `spend_totals`, because the
  typed `Select` is what an analysis needs if it wants to add its own filter rather than
  post-filter rows in Python.
- New direct tests: `test_card_service.py` (a partial redemption, a one-tap mark, three missed
  periods, urgency near the end of a month), `test_transaction_service.py`, and
  `test_spend_service.py` (refund netting, transfers and income excluded, and agreement with the
  dashboard rollup).
