# Quality score

One row per domain, graded A–D on four axes, every grade with the evidence behind it.
Graded 2026-09-27 (ticket 080). The weekly [doc-gardening](runbooks/doc-gardening.md) run
re-grades from the rubric below; **a grade changes only with evidence**, cited in the commit.

Domains are the rows of [ARCHITECTURE.md's domain map](ARCHITECTURE.md#domain-map).

| Domain | Invariant tests | Doc freshness | Layering | Known debt |
|---|---|---|---|---|
| [Net worth](#net-worth) | **A** | **A** | **A** | **C** |
| [Runway](#runway) | **B** | **A** | **A** | **A** |
| [Spending](#spending) | **B** | **A** | **A** | **A** |
| [Accounts & stakes](#accounts--stakes) | **A** | **A** | **C** | **B** |
| [Transactions & rules](#transactions--rules) | **B** | **A** | **C** | **B** |
| [CSV import](#csv-import) | **B** | **A** | **B** | **B** |
| [Sheet import](#sheet-import) | **B** | **A** | **A** | **C** |
| [Cards & perks](#cards--perks) | **A** | **A** | **C** | **B** |
| [Export & backup](#export--backup) | **B** | **A** | **B** | **C** |
| [Household & auth](#household--auth) | **D** | **A** | **B** | **C** |
| [Demo](#demo) | **B** | **A** | **A** | **C** |
| [Platform](#platform) | **A** | **A** | **A** | **B** |

**Where to spend effort first:** Household & auth's missing `/members` tests (TD-002), the
demo guard that can pass while checking nothing (TD-007), and the production restore drill
that gates real data (TD-003).

## Rubric

| Grade | Invariant tests | Doc freshness | Layering | Known debt |
|---|---|---|---|---|
| **A** | Each invariant has hand-computed expected values **and** generated or exhaustively parametrised cases | Design doc and spec checked against the code on the last-verified date; every known gap is written down | No violations, no allowlist entries | None open |
| **B** | Each invariant has a hand-computed or named edge-case test; no generated cases | Checked, with a minor claim unverified | Allowlisted, and the router's SQL is thin (a lookup or plain CRUD) | Low items only, or one medium |
| **C** | Functional coverage, but an invariant untested | A known false or stale claim | Allowlisted, and the router holds domain logic, not just queries | Several medium, or one high |
| **D** | Part of the surface has no functional test | No doc, or a doc that misleads | An unallowlisted violation | Several high |

"Invariant" means the rules in the domain's design doc and [core-beliefs](design-docs/core-beliefs.md).
Debt weights come from the [tech-debt tracker](exec-plans/tech-debt-tracker.md).

## Evidence

### Net worth

- **Tests A.** Hand-computed values across a stake change, a closed account, a stale
  snapshot and a missing snapshot (`test_net_worth.py`); generated stake histories and a
  parametrised never-exceeds-the-amount property (`test_ownership.py::test_invariant_holds_across_generated_histories`,
  `test_adjusted_value_never_exceeds_the_amount`); the in-memory series pinned to the
  single-date calculation, and its query count bounded (`test_net_worth_series.py`);
  Household ≥ Mine over 30 months of seed (`test_seed.py::test_household_net_worth_is_never_below_mine`).
- **Docs A.** [ownership-and-rounding](design-docs/ownership-and-rounding.md),
  [snapshots-and-carry-forward](design-docs/snapshots-and-carry-forward.md),
  [spec](product-specs/net-worth.md); the undrawn staleness signal is written down.
- **Layering A.** `routers/net_worth.py` calls services only; `test_architecture.py` finds
  no stake arithmetic outside `services/ownership.py`.
- **Debt C.** TD-010 (stale points served, never drawn), TD-013 (an order-sensitive series
  test that failed once).

### Runway

- **Tests B.** `test_runway.py`: the partial month does not depress burn, empty months are
  skipped not zeroed, the outlier rule and its configurability, ownership-adjusted liquid
  assets, zero burn reports no runway. Hand-computed; no generated cases.
- **Docs A.** [spec](product-specs/runway.md), [PRODUCT.md#burn-and-runway](PRODUCT.md#burn-and-runway).
- **Layering A.** `routers/runway.py` calls `services/runway.py` only.
- **Debt A.** None open.

### Spending

- **Tests B.** `test_api_spend.py`: transfers and income excluded, uncategorised its own
  bucket, not split by ownership, refunds reduce spend, equal-length prior period across a
  month boundary, hand-computed totals per category. No generated cases.
- **Docs A.** [transfers-and-categories](design-docs/transfers-and-categories.md), [spec](product-specs/spending.md).
- **Layering A.** `routers/spend.py` calls `services/spend.py` only.
- **Debt A.** None open.

### Accounts & stakes

- **Tests A.** `test_ownership.py` (half-open ranges, transitions, the 100% limit, generated
  histories), `test_api_accounts.py` (stake written on create, raw vs adjusted on a
  part-owned account, transition does not rewrite history), `test_balances.py` (same-day
  replace, carry-forward cap at exactly 90 days), `test_schema.py` (the constraints).
- **Docs A.** [data-model](design-docs/data-model.md), [ownership-and-rounding](design-docs/ownership-and-rounding.md),
  [spec](product-specs/accounts-and-stakes.md).
- **Layering C.** `routers/accounts.py` builds SQL and computes group totals itself,
  including the kind-blind `total_cents` (TD-001, TD-011).
- **Debt B.** TD-001 (medium), TD-011 (low).

### Transactions & rules

- **Tests B.** `test_categorize.py`: manual survives a full run, first match by priority,
  idempotent re-runs, no match leaves uncategorised, malformed and catastrophic regexes
  refused, the preview matches the description fallback. `test_api_transactions.py`: a
  manual override survives `/rules/apply`; bulk writes `manual`. No generated cases.
- **Docs A.** [transfers-and-categories](design-docs/transfers-and-categories.md), [spec](product-specs/transactions-and-rules.md).
- **Layering C.** `routers/rules.py`, `transactions.py` and `categories.py` build their own
  queries; `rules.py` loads rows for the preview itself (TD-001).
- **Debt B.** TD-001.

### CSV import

- **Tests B.** `test_csv_import.py`: identical rows get distinct ids and both survive,
  re-import changes nothing, a superset adds only the delta, amounts never parsed as float,
  the preview is the plan executed. Named edge cases; no generated cases.
- **Docs A.** [transactions-and-ingestion](design-docs/transactions-and-ingestion.md), [spec](product-specs/csv-import.md).
- **Layering B.** `routers/import_csv.py` imports `select` to look up the account; the
  planning lives in `services/csv_import.py`.
- **Debt B.** TD-001.

### Sheet import

- **Tests B.** `test_sheet_import.py` (40 tests): a blank cell is not zero, ambiguous
  layouts refused, a number in the mapping refused, a deliberately wrong total flagged,
  idempotent writes, the adjusted total differs for a part-owned account.
- **Docs A.** [spec](product-specs/sheet-import.md).
- **Layering A.** The script writes through `services/balances.record_balance`.
- **Debt C.** Never run for real: TD-003 (high), TD-004.

### Cards & perks

- **Tests A.** `test_perks.py` (57 cases from 33 functions): hand-computed windows for every
  cadence, month-end anchors across February, the leap day, boundary dates, negative
  indices, urgency at each cadence's threshold, calendar alignment for every month.
  `test_cards.py` (43 tests): idempotent marks, partial amounts, 409 on a used perk,
  history windows, the schedule endpoint. Component tests under `web/src/components/cards/`.
- **Docs A.** [card-perks-period-engine](design-docs/card-perks-period-engine.md) —
  corrected on 2026-09-27 for 076 and 079 — and [spec](product-specs/cards-and-perks.md).
- **Layering C.** `routers/cards.py` builds queries and holds the realised-value and
  history logic (`_realised_value`, `_realised_this_year`, `_history`) that belongs in
  `services/perks.py` (TD-001).
- **Debt B.** TD-001 (medium); TD-014 and TD-015 (low).

### Export & backup

- **Tests B.** `test_export.py`: every mapped table exported, money as strings, meta counts
  match, parents restored before children, self-referencing categories roots first. The
  full round trip is a performed drill, not a test (ADR 0008 explains why).
- **Docs A.** [ADR 0008](adr/0008-local-backups.md), [spec](product-specs/export-and-backup.md),
  [restore.md](../api/scripts/restore.md).
- **Layering B.** `routers/export.py` selects every table with no service — a generic dump.
- **Debt C.** TD-003: the production drill (high).

### Household & auth

- **Tests D.** Authentication is well covered — a stranger refused, a deactivated member
  refused on the next request, a missing or unverifiable assertion refused without saying
  which check failed, the dev identity ignored on a deployment (`test_deps_access_auth.py`),
  and a deployment without Access refusing to boot (`test_config.py`). But `/members` —
  create, duplicate email, deactivate, "cannot deactivate yourself" — has **no backend
  functional test** since 047b (TD-002).
- **Docs A.** [SECURITY.md](SECURITY.md#auth), [ADR 0007](adr/0007-drop-passkeys.md), [spec](product-specs/household-members.md).
- **Layering B.** `routers/users.py` is plain CRUD with its own queries (TD-001).
- **Debt C.** TD-002 (high), TD-009 (low).

### Demo

- **Tests B.** `test_demo_mode.py` walks the live app and asserts no declared route is
  writable; `check_demo_isolation.sh` has four self-tests. But the CI step that runs it can
  skip while reporting green (TD-007).
- **Docs A.** [ADR 0003](adr/0003-demo-isolation.md), [spec](product-specs/demo.md).
- **Layering A.** Middleware, not per-route checks.
- **Debt C.** TD-005 (not deployed), TD-007 (high once it is).

### Platform

The request path, the contract, health, logging, and the guards themselves.

- **Tests A.** Every shell guard has violating and clean fixtures (`scripts/test_guards.sh`);
  the doc checks likewise; `test_contract.py` (inventory, cents, basis points, auth on every
  route); `test_architecture.py` with self-tests; `web/src/lint-rules.test.ts`;
  `test_health.py`, `test_logging.py` (redaction through nested structures), `test_db.py`
  (commit and rollback); `make smoke`; two Playwright smoke tests.
- **Docs A.** [request-path](design-docs/request-path.md), [api-contract](design-docs/api-contract.md),
  [RELIABILITY.md](RELIABILITY.md), [FRONTEND.md](FRONTEND.md).
- **Layering A.** No violations.
- **Debt B.** TD-009, TD-015 (both low).
