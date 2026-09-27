# Account sources

Every account carries a `source`: `manual | csv | teller | plaid | simplefin`. v1 ships
`manual` and `csv` only. The aggregator values have been in the enum since the first
migration, so adding a connector needs no migration.

This is deliberate and it is the single most important sequencing decision in the project
([DECISIONS.md](../DECISIONS.md), 2026-08-14 "Foundational four": "V1 scope: manual + CSV
core, no connectors"). Institution aggregation is the part of this app with the *least*
control over it. As assessed in August 2026:

- Plaid's free trial caps at ~10 live Items.
- Teller's free tier is generous but covers no investment accounts.
- SimpleFIN is ~$15/yr, read-only, daily refresh.
- Fidelity has actively blocked aggregator access; Fidelity, Schwab, and JPMorgan have
  pushed aggregators into paid data deals. **401k and HSA are the worst-covered account
  categories in the entire ecosystem** — and they're a large share of the net worth here.
- CFPB's Section 1033 open banking rule was finalized Oct 2024, **enjoined** Oct 2025, and
  is mid-rewrite with "may data providers charge fees?" reopened.

Manual + CSV covers 100% of institutions including the ones no aggregator handles, works on
day one, and proves the entire application. Plaid and its peers also cost real money per
connection, break on bank UI changes, and require handing a third party access to every
account; CSV export is universal, free, and works offline. The cost is that importing is a
deliberate act rather than automatic — which, for a monthly review, is arguably the right
cadence anyway.

## The `SourceAdapter` interface

The plan was a `SourceAdapter` interface — `fetch_accounts()`, `fetch_balances()`,
`fetch_transactions()` — built in v1 with only `manual` and `csv` behind it, so connectors
become strictly additive.

**It was never built.** The enum values exist; the interface does not, and the CSV path
calls `services/csv_import.py` directly. The README and this doc used to say it existed.
Ticket 075 Phase 1 builds it, and moves the manual and CSV paths behind it so the
interface has two implementations before it has one consumer. Logged in
[tech-debt-tracker.md](../exec-plans/tech-debt-tracker.md).

## The first connector

[075 — SimpleFIN](../exec-plans/active/075-simplefin-connector.md) is planned, not built.
Its constraints drive its design: ≤24 requests a day (exceeding it disables the token, so
nothing ever fetches upstream on page load), 90 days per request, a 5-day overlap the
upsert makes free, `transacted_at` over `posted` for matching credits, and an Access URL
that is itself a credential. Protocol notes:
[references/simplefin-protocol-llms.txt](../references/simplefin-protocol-llms.txt).

**Real transaction history lands only after backups are proven.** Nightly connectors are
the point at which this database becomes the only copy of something. See
[SECURITY.md](../SECURITY.md#backups).
