# Core beliefs

The golden principles. Each is stated once, with why, and with what enforces it — a check
that fails the build, a test, or "prose only" when nothing mechanical does (those are the
ones a reviewer has to hold). Beliefs 1–10 were CLAUDE.md's non-negotiables; the rest were
scattered through the docs and tickets. AGENTS.md lists the first ten in one line each.

When a belief and the code disagree, the code is what runs — fix whichever is wrong, in the
same commit, and say which in the message.

## Data and privacy

### 1. Never commit real financial data

`data/` is gitignored (except its README); dev and tests run on generated synthetic data;
no fixture ever contains a real number. Git history is forever and public on a public repo.
**Enforced by:** `.gitignore`; `gitleaks` with `--redact` in CI; `import_sheet_history.py`
refuses a number in the committed mapping file (`test_sheet_import.py`); the seed refuses a
database whose `data_marker` says real (`test_seed.py::test_seed_itself_refuses_a_real_database`).

### 2. Code touches the data; context describes the data

Write a script that processes real files; never read real values into a session to work
with them. An import script parsing 500 rows is fine; pasting them into a prompt is not.
Schema design uses structure — headers, category names — never values.
**Enforced by:** prose only ([SECURITY.md](../SECURITY.md#handling-real-data-during-development)).
The doc checks skip `data/` entirely, so tooling never opens it either.

### 3. Do not run `/feedback`, `/bug` or `/share` in this repo

They upload conversation history, including code, retained for years.
**Enforced by:** prose only.

## Architecture

### 4. The browser never calls the API directly

All traffic goes to the Next.js origin, which proxies to a privately networked API. No
`NEXT_PUBLIC_API_URL`, no CORS. That is what makes the origin lock structural.
**Enforced by:** `scripts/check_no_public_api_url.sh`, `scripts/check_fly_api_private.sh`
(both API configs), the ESLint `fetch` rule, `make smoke`.
[request-path.md](request-path.md).

### 5. The Pydantic models are the API contract

`api-types.ts` is generated, committed, and never hand-edited; the frontend never
hand-writes a response type. After changing a response model, run `make types` and commit
the result.
**Enforced by:** `make types-check` in CI; the ESLint type-only-import rule;
`test_contract.py` (route inventory, integer cents and basis points, one error shape).
[api-contract.md](api-contract.md).

### 6. Layers point one way

API: models → schemas → services → routers → `main.py`; cross-cutting concerns enter
through `deps.py`. Web: `api-types` → `api.ts` → components → routes.
**Enforced by:** `api/tests/test_architecture.py` (shrink-only allowlist, TD-001);
`web/eslint.config.mjs`. [ARCHITECTURE.md](../ARCHITECTURE.md#layers).

### 7. One rule, one implementation

A rule the server computes — urgency, which period a date is in, a reset schedule,
ownership-adjusted subtotals, rule matches — is never re-derived in the browser or a second
service. Two implementations of one rule disagree eventually, and the disagreement looks
like a correct number.
**Enforced by:** tests where a second implementation exists on purpose
(`test_net_worth_series.py::test_the_series_agrees_with_the_single_date_calculation` pins
the in-memory stake lookup; `upcoming.test.tsx` asserts urgency follows the API flag);
otherwise prose only.

### 8. Demo mode is a separate deployment against a separate Neon project

Never a runtime flag over real data, never a branch of the real project. A flag is one bad
conditional away from serving real balances to the public.
**Enforced by:** `scripts/check_demo_isolation.sh` in `demo-guard.yml` (see TD-007 — it can
skip); `DemoReadOnlyMiddleware` and `test_demo_mode.py::test_no_declared_route_can_be_written_to`;
the demo Fly config must declare no Access and must set `DEMO_MODE` (CI).
[ADR 0003](../adr/0003-demo-isolation.md).

## Money and math

### 9. All money is `Decimal`, `NUMERIC(19,2)`, integer cents on the wire

Never float, anywhere, for any reason. Percentages are integer basis points.
**Enforced by:** `scripts/check_no_float.sh`; `test_schema.py::test_money_columns_are_numeric_19_2`
and `test_no_floating_point_column_anywhere`; `test_contract.py::test_money_fields_are_integer_cents`
and `test_no_schema_field_is_a_bare_float`; `test_csv_import.py::test_amounts_are_never_parsed_as_float`.
[ownership-and-rounding.md](ownership-and-rounding.md#money).

### 10. All net worth math is ownership-adjusted, and rounding happens once

In `services/ownership.adjust()`, per account, `ROUND_HALF_UP`, then sum — so a total always
equals the rows above it. No net worth figure is computed from raw balances.
**Enforced by:** `test_architecture.py` (no percentage or stake arithmetic outside
`ownership.py`); `test_ownership.py` (half-cent, and generated histories);
`test_net_worth.py` with hand-computed values. [ownership-and-rounding.md](ownership-and-rounding.md).

### 11. No implicit 100% stake

Every account gets an explicit stake row at creation; an absent row means "held nothing that
day", never "fully owned". With two possible owners the default is ambiguous.
**Enforced by:** `test_api_accounts.py::test_creating_an_account_writes_its_stake`;
`test_seed.py::test_every_account_has_an_explicit_stake`; `test_ownership.py::test_account_with_no_stake_row_returns_none`.

### 12. History is never rewritten

Stakes are effective-dated and half-open; a change closes one row and opens another. A
redemption stores its `period_start`. A user is deactivated, never deleted
(`ON DELETE RESTRICT`). Past figures must not move when present facts change.
**Enforced by:** `test_ownership.py::test_transition_does_not_rewrite_history`;
`test_api_accounts.py::test_stake_transition_does_not_rewrite_history`; the foreign key.

### 13. Liabilities are stored positive

Net worth subtracts them. A negative balance for debt makes every aggregate ambiguous.
**Enforced by:** `test_balances.py::test_liability_balances_are_stored_positive` and
`test_seed.py::test_liabilities_are_stored_positive` — they check the round trip; no
constraint refuses a negative.

### 14. Nothing that decides a date reads the clock

Period, urgency and history functions take the date as a parameter (routes default it to
today). The cases worth testing are specific days.
**Enforced by:** prose only; `services/perks.py` holds the rule, and `test_perks.py` tests
boundary days.

## Data integrity

### 15. Every balance write appends a snapshot

Through `services/balances.record_balance`, one row per account per date. History that isn't
captured is lost for good.
**Enforced by:** `test_balances.py`; `test_schema.py::test_one_snapshot_per_account_per_date`.
[snapshots-and-carry-forward.md](snapshots-and-carry-forward.md).

### 16. Ingestion is upsert, never insert

Keyed on `external_id` + account; a missing id is a content hash plus an occurrence index, so
two identical coffees stay two.
**Enforced by:** `test_csv_import.py::test_identical_rows_get_distinct_ids`,
`test_re_importing_the_same_file_changes_nothing`, `test_re_importing_a_superset_adds_only_the_new_rows`;
`test_schema.py::test_external_id_is_unique_per_account`.

### 17. A human decision outranks a pattern

Rules never overwrite a manual category; a rule matching nothing leaves a row uncategorised
rather than guessing.
**Enforced by:** `test_categorize.py::test_a_manual_category_survives_a_full_rule_run`,
`test_no_match_leaves_it_uncategorised`.

### 18. The request is the transaction boundary

Endpoints flush; `get_session` commits once, or rolls back on any exception. Found the hard
way: six endpoints returned 200 and persisted nothing.
**Enforced by:** `test_db.py::test_a_completed_request_commits`, `test_a_failed_request_rolls_back`.
[ADR 0005](../adr/0005-request-scoped-transactions.md).

## Security and operations

### 19. Absence of a check never reads as a passing one

Unconfigured Access refuses rather than admits; a deployment without Access does not start;
`DEV_IDENTITY_EMAIL` is ignored on https.
**Enforced by:** `test_config.py::test_a_deployment_without_access_refuses_to_boot`;
`test_deps_access_auth.py`.

### 20. Prefer the configuration that cannot silently degrade

No public address rather than a protected one; TLS Full (strict) that fails closed; a demo
that cannot reach real data rather than one told not to. Accept the louder failure.
**Enforced by:** `check_fly_api_private.sh`; prose for the Cloudflare settings
([ADR 0001](../adr/0001-hosting.md)).

### 21. Financial values are never logged or sent to Sentry

**Enforced by:** `test_logging.py` (redaction through nested structures);
`test_observability.py`.

### 22. A guard never prints what it protects

`check_demo_isolation.sh` never echoes a connection string; `gitleaks` runs with `--redact`.
**Enforced by:** prose only.

### 23. A backup is a restore that has been performed

An untested export is a file you believe in; a scheduled job that silently stops is worse
than a manual one that runs.
**Enforced by:** the drills table in [ADR 0008](../adr/0008-local-backups.md); `test_export.py`
(every table exported, parents restored before children).

## Process

### 24. Every plan ships unit and functional tests

**Enforced by:** prose only ([PLANS.md](../PLANS.md#tests)) and review. TD-002 is a gap.

### 25. Tests run on real, migrated Postgres

Never SQLite, never `create_all()` — a test must not pass against a schema production does
not have.
**Enforced by:** `api/tests/conftest.py` (migrates with `alembic upgrade head`);
`test_schema.py::test_upgrade_downgrade_upgrade_is_clean`.

### 26. Coverage is reported, never gated

A percentage gate is satisfied by tests that execute code without asserting anything.
**Enforced by:** CI reports coverage in the step summary with no threshold.

### 27. Guards test themselves

A guard that never fires looks exactly like one that is broken, so every guard runs against
a violating fixture and a clean one.
**Enforced by:** `scripts/test_guards.sh` (the shell guards), `scripts/test_check_docs.sh`
(the doc checks);
self-tests in `test_architecture.py` and `test_generate_docs.py`; `web/src/lint-rules.test.ts`.

### 28. Stub targets fail loudly

A no-op `make` target is indistinguishable from a passing one and hides unimplemented work.
**Enforced by:** the `not_yet` macro in the `Makefile`; declared-but-unimplemented routes
answer 501 (`test_contract.py::test_every_stub_returns_501`).

### 29. Migrations are reviewed by a human, one in flight at a time

Autogenerate misses CHECK constraints, partial indexes, enum changes and data migrations.
**Enforced by:** prose only ([PLANS.md](../PLANS.md#how-to-work-a-plan)); `make migrate`
prints the warning.

### 30. The docs are true, or the build fails

If a doc and the code disagree, the code wins and the doc is fixed in the same commit.
**Enforced by:** `scripts/check_docs.py` (links and anchors, reachability, indexes, plan
headers), `make docs-check` (generated docs), `test_contract.py` (the endpoint table).

### 31. Prefer boring

One household, two users, ever. If a design is justified by "what if there were a lot of
users", it is the wrong design. No Kubernetes, no Terraform, no queues, no caching layers.
**Enforced by:** prose only ([PRODUCT.md](../PRODUCT.md#explicit-non-goal-scale)).
