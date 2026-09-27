# The data model

Twelve tables. Columns, types, constraints and indexes are generated from the SQLAlchemy
metadata into [generated/db-schema.md](../generated/db-schema.md) — this doc is the *why*.
The two marked ★ are load-bearing: they are the reason this app is not a spreadsheet, and
getting them wrong means rewriting every aggregate query later.

| Table | Purpose | Design doc |
|---|---|---|
| `users` | The household; also the auth allowlist | [ownership-and-rounding.md](ownership-and-rounding.md#users) |
| ★ `ownership_stakes` | Who owns what share of each account, effective-dated | [ownership-and-rounding.md](ownership-and-rounding.md#ownership_stakes) |
| `institutions` | Banks, brokerages, lenders, 401k and HSA providers | below |
| `accounts` | Every asset and liability | below |
| ★ `balance_snapshots` | One balance per account per date; all history | [snapshots-and-carry-forward.md](snapshots-and-carry-forward.md) |
| `transactions` | Idempotently ingested money movements | [transactions-and-ingestion.md](transactions-and-ingestion.md) |
| `import_mappings` | Remembered CSV layouts per account | [transactions-and-ingestion.md](transactions-and-ingestion.md#import_mappings) |
| `categories` | The taxonomy, with a `kind` that keeps transfers out of spend | [transfers-and-categories.md](transfers-and-categories.md) |
| `categorization_rules` | Ordered merchant-pattern rules | [transfers-and-categories.md](transfers-and-categories.md#categories-and-rules) |
| `card_perks` | A recurring credit on a card | [card-perks-period-engine.md](card-perks-period-engine.md) |
| `perk_redemptions` | One row per period a credit was used | [card-perks-period-engine.md](card-perks-period-engine.md) |
| `data_marker` | Real or synthetic? One row | below |

## One upfront migration

The v1 schema — eleven tables — was created in **one hand-reviewed migration** (ticket
009, `0001_initial.py`). One upfront migration was a deliberate trade: Alembic's revision
chain is linear, so parallel branches each adding a migration produce a branched head that
has to be merged by hand. A single v1 schema removed that from the critical path entirely
and is what made Wave 2's three lanes safe. The cost was designing tables before writing
the code that used them.

It held. Post-v1 changes are incremental and serialised, one in-flight migration at a
time ([PLANS.md](../PLANS.md#how-to-work-a-plan)):

| Migration | Ticket | Change |
|---|---|---|
| `0001_initial` | 009 | The v1 schema, including a `credentials` table for passkeys |
| `0002_webauthn_challenges` | 034 | Passkey ceremony state |
| `0003_invitations` | 043 | Second-member invitations |
| `0004_drop_passkeys` | 047b | Drops `credentials`, `webauthn_challenges`, `invitations` ([ADR 0007](../adr/0007-drop-passkeys.md)) |
| `0005_card_perks` | 049 | `card_perks`, `perk_redemptions` |
| `0006_card_perk_amounts_and_fees` | 053 | Partial redemption amounts; `accounts.annual_fee`, `fee_renews_on` |

Every migration is reviewed by a human before merge. Autogenerate misses CHECK
constraints, partial indexes, enum value changes and every data migration — `make migrate`
says so when it runs.

Designing the schema before seeing the Google Sheet was low-risk for a stated reason
([DECISIONS.md](../DECISIONS.md), "Schema designed now, reconciled against the Google Sheet
during the import ticket"): the structurally risky parts — effective-dated ownership,
snapshot history, idempotent ingestion — are generic. What the sheet determines is the
category taxonomy and account naming, which are data, not schema.

## `institutions`

Banks, brokerages, lenders, 401k and HSA providers. Mostly a display grouping.

## `accounts`

Every asset and liability. Key columns:

- `kind` — `liquid_asset | illiquid_asset | liability`
- `subtype` — `checking | savings | brokerage | 401k | hsa | real_estate | credit_card | mortgage | auto_loan | ...`
- `source` — `manual | csv | teller | plaid | simplefin` — see [account-sources.md](account-sources.md)
- `currency` — `CHECK (currency = 'USD')`. Stored so the constraint can be relaxed later;
  multi-currency itself is Rejected in [PRODUCT.md](../PRODUCT.md#rejected), because
  summing mixed currencies silently produces a wrong number.
- `closed_at` — nullable. See [closed accounts](snapshots-and-carry-forward.md#closed-accounts-and-carry-forward).
- `annual_fee`, `fee_renews_on` — nullable, credit cards in practice (ticket 053).
  Documented rather than constrained: Postgres cannot cheaply enforce "only when
  subtype = credit_card", and a side table for two columns buys a join and nothing else.

**Liabilities are stored as positive balances** with `kind = liability`. Net worth
subtracts them. Do not store negative balances to represent debt — it makes every
aggregate ambiguous. Nothing in the schema refuses a negative; the rule is held by the
write paths and by `test_balances.py::test_liability_balances_are_stored_positive`.

**Current balance is derived** as the latest snapshot, never duplicated onto `accounts`.
That removes a whole class of consistency bug; accept the join.

**A credit card is an account** (ticket 067). Its balance is debt and has to count in net
worth, which is what `AccountKind.LIABILITY` is for. A separate `cards` table would either
duplicate those rows or drop cards out of net worth, and two lists of the same cards
disagree the first time one is renamed or closed. The cards screen hides this; the schema
does not.

Every child of `accounts` is `ON DELETE CASCADE` — stakes, snapshots, transactions, import
mappings, perks and redemptions. Deleting an account destroys its history, which is why
the UI offers closing first and demands the name before deleting (ticket 063).

## `data_marker`

A single row recording whether this database holds real or synthetic data. The synthetic
seed script refuses to run against a database marked real — so a mistyped app name or
connection string fails rather than overwriting real history. See
[SECURITY.md](../SECURITY.md#demo-isolation).
