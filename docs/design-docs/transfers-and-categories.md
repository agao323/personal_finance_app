# Transfers and categories

The machinery that makes spending numbers believable. Code:
`api/app/services/categorize.py`, `api/app/services/spend.py`,
`api/app/routers/{rules,transactions,categories}.py`.

## Transfers

A transfer from checking to brokerage is not spending. If it shows up as spending, every
number on the dashboard loses credibility, and runway is wrong in the direction that
matters.

Two mechanisms:

- **`categories.kind`** — `income | expense | transfer`. Spend rollups filter to
  `expense`. Income is classified so it stays *out* of the rollups; it isn't displayed in
  v1. A rule can target a `transfer`-kind category, which is how transfers get classified
  in bulk.
- **`transactions.transfer_group_id`** — nullable, links the two sides of a matched pair.
  Set by hand in v1 from the transactions screen (`POST /transactions/bulk-transfer`).
  Automatic pair detection is Later ([PRODUCT.md](../PRODUCT.md#later--intended-unscheduled)).

Neither existed in the original plan, which assumed transfers would be excluded without
saying how ([DECISIONS.md](../DECISIONS.md), "Burn is gross spend; transfers and closed
accounts are modelled explicitly").

**Burn is gross spend excluding transfers; income is not netted.** Runway answers "how
long if income stopped", which is the only version worth a tile while income is coming
in ([PRODUCT.md](../PRODUCT.md#burn-and-runway)).

## Categories and rules

Imported categories are mediocre. A user-editable rule set — merchant pattern → category,
ordered, first match wins — is what makes the spend breakdowns trustworthy enough to act
on. Without it every spending chart is subtly wrong and the app quietly stops getting used.

Rules carry a pattern, a match type (`contains | equals | starts_with | regex`), a target
category, and a priority. Four properties hold, and each is load-bearing
(`categorize.py`'s docstring has the full argument):

1. **A manual category is never overwritten.** `apply_rules` skips any row whose
   `category_source` is `manual`, unconditionally. This is the entire reason
   `category_source` exists, and ticket 023 is what writes `manual` — the protection and
   that write path are only meaningful as a pair.
2. **Order is total and deterministic.** Priority ascending, ties broken by id (creation
   order). Without the tie-break, re-running could give a different answer each time.
3. **Re-running over all history is idempotent.** A row is written only when the result
   would actually change.
4. **Re-running is never destructive.** No match leaves a transaction uncategorised — a
   real state the spend view surfaces as the prompt to write a rule. Deleting a rule does
   not clear the categories it set; an accidental apply against an empty rule set must not
   wipe every category in the database.

**The subject** a rule matches is the merchant, falling back to the description when the
merchant column is empty (`subject_of`).

**Regex patterns are untrusted code.** Malformed ones are refused when written (422).
Catastrophic backtracking is bounded three ways — nested quantifiers rejected at write
time, the subject truncated, and a wall-clock budget between transactions — none of which
is a proof. A hard guarantee needs RE2 or the `regex` module's timeout; revisit if patterns
ever come from anyone but the household.

**The match preview runs the engine itself** (`POST /rules/preview`, ticket 033), not a
`LIKE` query: an approximation agrees with the engine right up until the pattern gets
subtle enough to need checking, and a merchant-column `LIKE` misses description fallbacks
entirely. It reports `already_manual`, so "matches 40" is not read as a promise to change 40.

## The loop

Spending surfaces uncategorised spend → the transactions screen fixes it by hand (writing
`manual`) → a rule, prefilled from the row's merchant, keeps it fixed. Hiding uncategorised
would make the chart prettier and the numbers worse. See
[product-specs/transactions-and-rules.md](../product-specs/transactions-and-rules.md).

## Tested by

`test_categorize.py` (priority order, manual survival, idempotence, no-match),
`test_api_transactions.py` (a manual override survives `POST /rules/apply`; bulk writes
`manual`), `test_api_spend.py` (a transfer pair never appears; uncategorised always does).
