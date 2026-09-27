# 082 — Card, perk and transaction reads move from routers into services
Status: todo
Wave: 9   Lane: —
Touches: none (no contract change, no migration)
Blocked by: none
Read first: docs/ADVISOR.md#principles, docs/adr/0006-contract-changes-during-wave-2.md

## Goal
The read logic that lives inline in routers moves into services, so an advisor tool and a screen
call **one** implementation. Nothing a user sees changes.

## Acceptance criteria
- [ ] `services/cards.py` holds the card list with perks and current periods, upcoming perks, the
      history walk including `missed_periods`, `_realised_value` and realised-this-year — all
      moved from `routers/cards.py`, which becomes a thin mapper to schemas.
- [ ] `services/transactions.py` holds `search(session, filters, limit, offset)` returning rows and
      a total — moved from `routers/transactions.list_transactions`.
- [ ] `services/spend.py` exposes `expense_rows(session, start, end)` and
      `spend_totals(session, start, end, by_parent)` — today's private `_spend_query` and `_totals`
      — so analyses reuse the transfer, refund, income and uncategorised rules instead of
      restating them.
- [ ] Behaviour identical: every existing test passes **unchanged**, and `make types` produces no
      diff.
- [ ] Tests: unit tests for each newly public function on synthetic fixtures with hand-computed
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
