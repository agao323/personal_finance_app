# Product specs

One spec per shipped feature: what the user can do, the rules and edge cases, the screens,
the endpoints, and the tickets that built it. The *why* behind a rule lives in the linked
design doc; the intent, non-goals, Later and Rejected lists live in
[PRODUCT.md](../PRODUCT.md). A check fails if a spec in this folder is missing from this
page.

| Spec | In one line | Screens | Status |
|---|---|---|---|
| [net-worth.md](net-worth.md) | Ownership-adjusted net worth now and over time, Mine or Household | `/` | shipped |
| [spending.md](spending.md) | Spend by category for a period, with drill-down and prior-period comparison | `/spending` | shipped |
| [runway.md](runway.md) | Months of liquid assets at trailing gross burn | `/` | shipped |
| [accounts-and-stakes.md](accounts-and-stakes.md) | Accounts, balances, effective-dated ownership, closing and deleting | `/accounts`, `/accounts/[id]`, `/accounts/new` | shipped |
| [transactions-and-rules.md](transactions-and-rules.md) | Filter, recategorise, mark transfers; the rules engine and its screen | `/transactions`, `/rules` | shipped |
| [csv-import.md](csv-import.md) | Upload, map, preview the plan, commit — idempotently | `/import` | shipped |
| [sheet-import.md](sheet-import.md) | One-off import of the Google Sheet's balance history | none (a script) | built; not yet run for real |
| [cards-and-perks.md](cards-and-perks.md) | Cards, their recurring credits, what is about to expire, and whether a card pays for itself | `/cards`, `/cards/[id]` | shipped |
| [export-and-backup.md](export-and-backup.md) | Every table as JSON, from the browser or to the owner's disk, and back | none (`GET /export`, `make backup`) | shipped; production drill pending |
| [household-members.md](household-members.md) | Adding, deactivating and signing out household members | `/settings/household` | shipped |
| [demo.md](demo.md) | A public, read-only deployment on synthetic data | the whole app, read-only | code shipped; not deployed |

Planned, not shipped: SimpleFIN transactions and credits marked from them
([075](../exec-plans/active/075-simplefin-connector.md)); catalogue-seeded credits
([060](../exec-plans/active/060-seeding-a-cards-perks-from-a-catalogue.md), awaiting a decision).
