# Accounts and stakes

Every asset and liability, its balance history, and who owns what share of it, when.

## What you can do

- **List accounts** grouped into liquid assets, illiquid assets and liabilities, with group
  subtotals. Wherever a stake splits an account, the **ownership-adjusted and raw values sit
  side by side** — that is the feature that makes this app different from an off-the-shelf
  one. Closed accounts are collapsed into their own section. Stale balances carry a badge
  and a prompt to update. An empty list routes to import.
- **Open an account** to see a balance-history sparkline (labelled raw — the history takes
  no view scope), the stake history **with its effective dates**, and recent transactions.
- **Create or edit an account**: name, institution (created or reused by name), kind,
  subtype, optionally an opening balance and a partial stake.
- **Record a balance** for any date (defaults to today).
- **Change a stake**. The form says in plain language what will happen — "this closes the
  current stake on <date> and opens a new one; your past net worth won't change" — and
  previews the resulting stake history with the new row marked.
- **Close an account**: it stops counting from that date; history and transactions stay;
  nothing is deleted.
- **Delete an account**, only after typing its name, from a dialog that states what goes by
  count — balance snapshots, transactions, credits, recorded uses — read from the API.
  Closing is offered first.

## Rules and edge cases

- **Every account gets an explicit 100% stake** at creation, for the creator unless a
  partial stake is given. There is no implicit default
  ([ownership-and-rounding](../design-docs/ownership-and-rounding.md)).
- **Stakes are effective-dated and half-open.** A change closes the old row on the change
  date and opens a new one; a change dated at or before a stake's start replaces it. Stakes
  overlapping any date may not exceed 100% (422).
- The stake table shows the **last day** a stake applied (the day before `effective_to`),
  not the raw exclusive bound, which would print the same date twice.
- **Recording twice on the same date replaces** that day's balance.
- **Liabilities are entered and stored positive.**
- Money inputs are text, parsed by splitting the string; a half cent rounds away from zero,
  matching the server. Percentages are entered as percent and sent as basis points.
- The list's group subtotals come from the API; the browser never re-sums or re-rounds
  them. There is **no grand total** on the list — net worth is a dashboard figure with one
  source (the API's `total_cents` is TD-011).
- **Deletion cascades** to stakes, snapshots, transactions, import mappings, perks and
  redemptions. Snapshots cannot be rebuilt from a bank, which is why the name is required.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET POST | `/accounts` | List with raw and adjusted subtotals; create (writes the stake in the same transaction) |
| GET PATCH | `/accounts/{account_id}` | Detail with stake history; rename, close (`closed_at`), annual fee |
| GET | `/accounts/{account_id}/history` | The snapshot series |
| POST | `/accounts/{account_id}/balances` | Record a balance through `record_balance` |
| POST | `/accounts/{account_id}/stakes` | Transition a stake atomically |
| GET | `/accounts/{account_id}/deletion-preview` | Counts of everything a delete would remove |
| DELETE | `/accounts/{account_id}` | Refused unless the request names the account exactly |

## Screens and code

`web/src/app/(dashboard)/accounts/` (`page.tsx`, `[id]/page.tsx`, `new/page.tsx`) —
`components/account-row.tsx`, `components/forms/{account,balance,stake}-form.tsx`,
`fields.tsx`, `charts/sparkline.tsx`. API: `routers/accounts.py`, `services/accounts.py`,
`services/ownership.py`, `services/balances.py`.

## Built by

010 (stakes), 011 (snapshots), 019 (the API), 029 (screens), 031 (forms), 063 (deleting,
with a warning that means it).
