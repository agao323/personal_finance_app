# 063 — Remove a card, with a warning that means it
Status: todo
Wave: 7   Lane: —
Blocked by: none

## Goal
Delete a card account. There is currently no way to remove one at all.

## What is actually at stake

Every child of `accounts` is `ON DELETE CASCADE`: **ownership stakes, balance snapshots,
transactions, import mappings, card perks, and every redemption recorded against them.**
Deleting a card does not tidy a list — it destroys that account's entire financial history,
and balance snapshots are the one class of data in this app that cannot be reconstructed
from a bank.

**And there is no backup.** Ticket 017's schedule is off and its secrets are unset, so
there is nothing to restore from. This is the most destructive action in the product and it
is being added at the moment the safety net is least present. The warning has to carry that.

## Acceptance criteria
- [ ] `DELETE /accounts/{account_id}`, cascading as the schema already specifies
- [ ] **Refused unless the request names the account**, so a mis-click cannot destroy
      history. Typing the card's name is the confirmation
- [ ] The dialog states what goes, by count and by kind: N balance snapshots, N
      transactions, N credits, N recorded uses — **read from the API, not guessed**. A
      warning that says "all data" is ignored; one that says "312 balance snapshots going
      back to March 2024" is read
- [ ] It says plainly that this cannot be undone and that no backup exists yet
- [ ] **Closing a card is offered first.** `closed_at` removes it from net worth and keeps
      the history, and it is what most people actually want
- [ ] Tests: the name must match; the counts are accurate; cascade removes the children;
      closing is offered as the alternative

## Files
- `api/app/routers/accounts.py`, `api/app/schemas/account.py`
- `web/src/components/cards/remove-card.tsx`

## Notes

`ownership_stakes.owner_user_id` is `ON DELETE RESTRICT` — that protects *users*, not
accounts. `account_id` cascades. Both are deliberate and this ticket changes neither.
