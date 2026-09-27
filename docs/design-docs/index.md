# Design docs

Why the system is built the way it is. Three kinds, all listed here — a check fails if a
file in `design-docs/` or `adr/` is missing from this page:

- **Design docs** (this folder): one per deep topic, kept current. Edit them when the code
  changes.
- **ADRs** ([adr/](../adr/README.md)): one decision each, made during implementation.
  Immutable history — fix links, add a "superseded by" banner, never rewrite the decision.
- **[DECISIONS.md](../DECISIONS.md)**: the project-level decisions made before coding,
  append-only.

**Last verified** is the date someone checked the doc's claims against the code, not the
date it was edited. The weekly [doc-gardening](../runbooks/doc-gardening.md) run bumps it
only for what it actually checked.

## Design docs

| Doc | Summary | Status | Last verified | Enforced by |
|---|---|---|---|---|
| [core-beliefs.md](core-beliefs.md) | The golden principles, each with why and what enforces it | current | 2026-09-27 | per belief, in the doc |
| [request-path.md](request-path.md) | Browser → Next.js BFF → private API over `.internal`; no CORS, one Access app | current | 2026-09-27 | `check_no_public_api_url.sh`, `check_fly_api_private.sh`, ESLint `fetch` rule, `make smoke` |
| [api-contract.md](api-contract.md) | Pydantic → OpenAPI → `api-types.ts`; the endpoint table; re-freezing | current | 2026-09-27 | `make types-check`, `test_contract.py` |
| [data-model.md](data-model.md) | The twelve tables, the one-migration trade, migration history | current | 2026-09-27 | `test_schema.py`, `make docs-check` (db-schema) |
| [ownership-and-rounding.md](ownership-and-rounding.md) | Effective-dated stakes, household visibility, money as cents, round once | current | 2026-09-27 | `test_ownership.py`, `test_architecture.py`, `check_no_float.sh`, `test_net_worth_series.py` |
| [snapshots-and-carry-forward.md](snapshots-and-carry-forward.md) | Every balance write appends; 90-day cap; closed accounts | current | 2026-09-27 | `test_balances.py`, `test_net_worth.py` |
| [transactions-and-ingestion.md](transactions-and-ingestion.md) | Upsert with occurrence-indexed ids; the preview is the plan; sheet import | current | 2026-09-27 | `test_csv_import.py`, `test_sheet_import.py`, `test_schema.py` |
| [transfers-and-categories.md](transfers-and-categories.md) | `categories.kind`, transfer pairs, the rules engine and its four properties | current | 2026-09-27 | `test_categorize.py`, `test_api_spend.py`, `test_api_transactions.py` |
| [card-perks-period-engine.md](card-perks-period-engine.md) | Periods from an anchor that sets phase; urgency; realised value | current | 2026-09-27 | `test_perks.py`, `test_cards.py` |
| [account-sources.md](account-sources.md) | Manual and CSV first; `SourceAdapter` never built; SimpleFIN planned | current | 2026-09-27 | `test_schema.py::test_source_enum_ships_connectors_not_yet_implemented`; otherwise prose only |
| [hosting.md](hosting.md) | Neon, Fly, Cloudflare; demo caching; cost; why not Kubernetes | current | 2026-09-27 | `check_fly_api_private.sh`, `demo-guard.yml`; Neon and Cloudflare settings are prose only |

## ADRs

| ADR | Summary | Status | Last verified | Enforced by |
|---|---|---|---|---|
| [0001 — Hosting](../adr/0001-hosting.md) | Fly + Neon, API on `.internal` only, release-command migrations, TLS Full (strict) | current (its backup layer replaced by 0008) | 2026-09-27 | `check_fly_api_private.sh` |
| [0002 — Auth](../adr/0002-auth.md) | Cloudflare Access in front, passkeys inside, private origin | superseded in part by 0007 — the Access half stands | 2026-09-27 | `test_deps_access_auth.py`, `proxy.test.ts`, [access-verification](../runbooks/access-verification.md) |
| [0003 — Demo isolation](../adr/0003-demo-isolation.md) | Separate Neon project, not a branch or a flag | current; verification pending (TD-005) | 2026-09-27 | `check_demo_isolation.sh`, `test_demo_mode.py` |
| [0004 — Backups to R2](../adr/0004-backups.md) | Encrypted nightly dumps to R2 with a dead-man's switch | superseded by 0008 | 2026-09-27 | — |
| [0005 — Request-scoped transactions](../adr/0005-request-scoped-transactions.md) | The request is the transaction boundary | current | 2026-09-27 | `test_db.py` |
| [0006 — Contract changes in Wave 2](../adr/0006-contract-changes-during-wave-2.md) | Four additive re-freezes, then 047b's removal | current | 2026-09-27 | `make types-check`, `test_contract.py` |
| [0007 — Drop passkeys](../adr/0007-drop-passkeys.md) | Access is the authentication; `users` is the allowlist | current | 2026-09-27 | `test_deps_access_auth.py`, `test_auth.py`, `test_config.py` |
| [0008 — Local backups](../adr/0008-local-backups.md) | JSON export to the owner's machine; no offsite copy we operate | current; production drill pending (TD-003) | 2026-09-27 | `test_export.py`, the drills table |

## Project decisions

| Doc | Summary | Status | Last verified | Enforced by |
|---|---|---|---|---|
| [DECISIONS.md](../DECISIONS.md) | Household not single user, BFF, 2dp money, gross burn, Neon, waves and lanes, the backend/frontend split, v1 scope | current; entries carry their own superseded banners | 2026-09-27 | prose only — the mechanisms are listed in [core-beliefs.md](core-beliefs.md) |
