# Product

The durable statement of what this is and why. Written once; changes only when intent changes.

## What

A personal finance web app for one household — Allen Gao today, with a partner as a second
user later. It replaces a manually-maintained Google Sheet with a real application: net
worth, assets, liabilities, expenses, spending categories, and runway — with good data
visualization.

## Two goals, in tension, both real

**1. Actually manage my money.** The app must be good enough that I stop using the spreadsheet.
That is the only real test of success. A feature I don't use every month is a feature that
shouldn't have been built.

**2. Learn to take a project from 0 to 1.** Deployment, hosting, containers, databases,
picking services and understanding why. Growing as a software engineer is an explicit goal,
not a side effect. Where a decision trades "ship faster" against "learn more," the tie
goes to learning — *except* where it delays v1, because an unshipped app teaches nothing.

## Explicit non-goal: scale

**One household. Two users, maximum, ever.** No multi-tenancy, no horizontal scaling, no
caching layers, no message queues, no microservices.

The second user is a data-model requirement — ownership stakes belong to a person, and net
worth is computed per viewer — not a product surface. There are no invitations, no roles, no
permissions UI, and no per-account privacy. Both users see every account; only the money
splits. See [ARCHITECTURE.md](ARCHITECTURE.md#users-and-ownership).

Building for scale here is wasted effort. If a design decision is justified by "what if there
were a lot of users," it is the wrong decision.

## Security posture

This app holds a complete picture of one household's finances. That makes it a higher-value
target than its user count suggests.

- Nobody outside the household can reach the real application. Not by URL guessing, not by
  session theft.
- Nobody can read the numbers in transit or at rest.
- The demo is public *by design* and therefore must contain no real data whatsoever —
  enforced by infrastructure, not by a feature flag.

Full threat model in [SECURITY.md](SECURITY.md).

## Craft bar

This should hold up as a real project rather than a weekend script, and it should still make
sense to me a year from now when I've forgotten why any of it works the way it does. That
constrains the design:

- A **demo deployment** with generated synthetic data, publicly linkable, no auth.
  Separate Neon project. The real app's data cannot reach it.
- README with an architecture diagram, tests, CI, real migrations, and a setup path that
  works from a clean clone.
- **ADRs recording why decisions were made, as they're made.** A first-class deliverable, not
  documentation debt. Being able to reconstruct a trade-off six months later is the difference
  between a codebase I own and one I merely possess — and it's what stops a future session
  from re-litigating a settled question.

## Feature vision

Grouped by conviction. **v1** is committed. **Later** is intended but unscheduled.
**Rejected** is recorded so it doesn't get re-litigated.

### v1 — committed

- Accounts across all categories: liquid assets, non-liquid assets, liabilities.
- **Fractional ownership.** If I own 50% of an asset, 50% counts toward my net worth. Same
  for liabilities. Effective-dated, per user. A data-model requirement, not a display feature.
- Balance history via snapshots → net worth over time.
- Manual entry and CSV import for every account type.
- Transaction categorization with a user-editable rules engine, **including the screens to
  edit rules and to override a category by hand.**
- A transactions screen with filtering and inline recategorisation.
- Dashboard: current net worth, runway/burn, net worth over time, spend by category MTD/YTD.
- Passkey auth + Cloudflare Access.
- Public demo deployment on synthetic data.
- Nightly encrypted backups with a restore that has actually been performed.

### Burn and runway

**Burn is gross spend, excluding transfers. Income is not netted out.** Runway is
ownership-adjusted liquid assets divided by trailing gross burn — it answers "how long if
income stopped," which is the only version of the question worth a dashboard tile while
income is coming in. Income is still classified (so it stays out of the spend rollups) but
is not displayed in v1.

### Later — intended, unscheduled

- **Institution connectors** (Teller / SimpleFIN / Plaid) behind the `source` abstraction.
  Deliberately not in v1: see [ARCHITECTURE.md](ARCHITECTURE.md#account-sources) for why
  this is the least controllable part of the project.
- **Income and cashflow views**, and net burn alongside gross.
- **Credit card optimization:** which card to use per purchase (category → multiplier rules
  engine, incl. rotating quarterly categories); tracking rewards I'm not capturing; total
  credit limit; subscriptions I should cancel.
- **Credit score over time** — manual monthly entry + chart. There is no legitimate consumer
  API for this; do not attempt to integrate one.
- **FIRE projections.** Must model taxable vs. tax-deferred vs. Roth split, sequence-of-returns
  sensitivity, and pre-65 healthcare cost. Output a withdrawal-rate sensitivity band, not a
  single number. A calculator that just multiplies expenses by 25 is not worth building.
- **Holdings-level tracking** (shares × price). Would require a second precision regime —
  balances are 2dp, prices are not. Out of scope until it's actually wanted.
- **Automatic transfer-pair detection.** v1 marks transfers by category and by hand.
- **AI agent** over my finances — ask questions, get recommendations. Highest risk feature in
  the project; ships last, under the constraints in [SECURITY.md](SECURITY.md#ai-agent).

### Rejected

- **Sign-up bonus tracking / "which card should I apply for."** No maintained free data source.
  Becomes a scraping treadmill producing stale data, which is worse than no data. If revisited,
  the honest version is a hand-curated file updated a few times a year.
- **Customizable / drag-and-drop dashboard layouts.** Multi-week sink. One household, who can
  edit the code.
- **Multi-currency.** `currency` is stored but constrained to USD. Summing mixed currencies
  silently produces a wrong number; a stored field the math ignores is worse than no field.
- **Kubernetes as initial infrastructure.** See [ARCHITECTURE.md](ARCHITECTURE.md#why-not-kubernetes).
  Optionally revisited later as a deliberate learning exercise, after the app works.
- **Real-time balance updates.** Not a thing that exists. Aggregators are daily batch.
  The mental model is nightly sync plus a manual refresh button.
