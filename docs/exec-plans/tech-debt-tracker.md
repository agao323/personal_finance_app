# Tech-debt tracker

Known debt that is not a plan yet. Each item has a stable ID that code and tests may cite —
`api/tests/test_architecture.py`'s allowlist does, and fails if an ID it cites is missing
here. **Never renumber.** Close an item by moving it to [Closed](#closed) with the commit
that fixed it.

Add an item when you find debt outside your plan's scope ([PLANS.md](../PLANS.md#how-to-work-a-plan)).
Promote it to a plan in `active/` when someone is going to do it. The weekly
[doc-gardening](../runbooks/doc-gardening.md) run reads this list.

| ID | Debt | Kind | Weight |
|---|---|---|---|
| [TD-001](#td-001--eight-routers-build-sql-themselves) | Eight routers build SQL themselves | layering | medium |
| [TD-002](#td-002--members-has-no-backend-functional-tests) | `/members` has no backend functional tests | test gap | **high** |
| [TD-003](#td-003--the-production-restore-drill-has-not-been-run) | The production restore drill has not been run | owner action | **high** — gates 024 and 075 |
| [TD-004](#td-004--024-stalled-on-td-003) | 024 stalled on TD-003 | stalled plan | follows TD-003 |
| [TD-005](#td-005--037s-infrastructure-half-was-never-done) | 037's infrastructure half was never done | stalled plan | medium |
| [TD-006](#td-006--039-waits-on-037-and-on-a-cold-machine) | 039 waits on 037 and on a cold machine | stalled plan | low |
| [TD-007](#td-007--the-demo-guard-compares-against-a-retired-secret) | The demo guard compares against a retired secret | CI / config | **high once 037 lands** |
| [TD-008](#td-008--060-waits-on-a-decision) | 060 waits on a decision | decision | low |
| [TD-009](#td-009--passkey-leftovers-in-dependencies-and-config) | Passkey leftovers in dependencies and config | cleanup | low |
| [TD-010](#td-010--the-series-staleness-signal-is-served-and-never-drawn) | The series' staleness signal is served and never drawn | feature gap | medium |
| [TD-011](#td-011--accountlist-totals-sum-across-kinds) | `AccountList` totals sum across kinds | contract | low |
| [TD-012](#td-012--sourceadapter-was-specified-and-never-built) | `SourceAdapter` was specified and never built | design gap | low until 075 |
| [TD-013](#td-013--an-order-sensitive-series-test-is-flaky) | An order-sensitive series test is flaky | test | medium |
| [TD-014](#td-014--done-plans-with-unticked-acceptance-boxes) | Done plans with unticked acceptance boxes | records | low |
| [TD-015](#td-015--the-stub-ratchet-is-dormant) | The stub ratchet is dormant | dormant code | low |

A sweep for `TODO`, `FIXME`, `XXX` and `HACK` markers across `api/`, `web/`, `scripts/` and
the workflows on 2026-09-27 found **none** — this repo writes the reason into a comment or a
plan instead.

## Open

### TD-001 — Eight routers build SQL themselves

- **Where:** `api/app/routers/{accounts,cards,categories,export,import_csv,rules,transactions,users}.py`
  import `select`, `func`, `delete`, `text` or `Table` and query directly. `cards.py` also
  holds real logic (`_realised_value`, `_realised_this_year`, `_history`).
- **Why it matters:** the layer map ([ARCHITECTURE.md](../ARCHITECTURE.md#layers)) puts
  queries in services. A rule living in a router cannot be reused by a second caller — a
  connector, a script, a second endpoint — without being copied, and two copies drift.
- **Held by:** `api/tests/test_architecture.py`, whose allowlist names exactly these eight
  files and may only shrink. A new router that builds SQL fails the suite.
- **Next step:** when a plan touches one of these routers, move its queries into a service
  and delete the allowlist entry in the same commit. Not worth a plan of its own.
- **Found:** 2026-09-27, ticket 080.

### TD-002 — `/members` has no backend functional tests

- **Where:** `api/app/routers/users.py` (`GET/POST /members`, `PATCH /members/{member_id}`).
  Ticket 047b deleted `api/tests/test_invitations.py` with the passkey layer, and it was the
  only file exercising these routes. `test_contract.py` only checks they exist and require
  authentication.
- **Still covered:** that a deactivated member is refused on the next request
  (`test_deps_access_auth.py::test_a_deactivated_member_is_refused_on_the_next_request`),
  and the household screen against MSW (`settings/household/page.test.tsx`).
- **Not covered:** creating a member, a duplicate email, deactivating and reactivating,
  and "you cannot deactivate yourself" — the rule that stops a one-member household locking
  itself out.
- **Why it matters:** [PLANS.md](../PLANS.md#tests) — every plan ships functional tests.
  These routes decide who can see the household's finances.
- **Next step:** a small plan adding `api/tests/test_api_members.py`.
- **Found:** 2026-09-27, ticket 080.

### TD-003 — The production restore drill has not been run

- **Where:** the pending row in [ADR 0008](../adr/0008-local-backups.md#restore-drills).
  The first drill (2026-09-27) passed against synthetic data and found a real bug.
- **Why it matters:** [SECURITY.md](../SECURITY.md#backups) — no real data enters
  production until a restore has been proven against real data. It gates 024 and 075.
- **Next step:** the owner runs [going-live §C](../runbooks/going-live.md#c--ticket-017--backups-and-a-tested-restore).
  It cannot be done by an agent: it needs the production connection string, and the export
  must never be read into a session.
- **Found:** 2026-09-27, ticket 080 (from 017, 024 and 075).

### TD-004 — 024 stalled on TD-003

- **Where:** [024](active/024-google-sheet-history-import.md), `in-progress` since
  2026-08-19. The script, the mapping format and 40 tests are done. Its other blockers (036,
  011, 019) are done.
- **Next step:** after TD-003, the owner follows [going-live §D](../runbooks/going-live.md#d--ticket-024--import-your-spreadsheet-history).
  Until it runs, the Google Sheet stays the system of record — which is the v1 definition
  of done not being met.
- **Found:** 2026-09-27, ticket 080.

### TD-005 — 037's infrastructure half was never done

- **Where:** [037](active/037-demo-deployment.md), `in-progress` since 2026-08-19. The code
  is done (read-only middleware, banner, configs, guard, ADR 0003). Not done: a second Neon
  project, the Fly apps, DNS and the cache rule, the `DEMO_DATABASE_URL` secret, and the
  five checks in [ADR 0003](../adr/0003-demo-isolation.md#verification).
- **Next step:** owner action, [going-live §E](../runbooks/going-live.md#e--ticket-037--the-public-demo)
  — and resolve TD-007 first, or the guard will not enforce anything.
- **Found:** 2026-09-27, ticket 080.

### TD-006 — 039 waits on 037 and on a cold machine

- **Where:** [039](active/039-readme-architecture-diagram-and-adr-backfill.md). Open: the
  live demo link (needs 037) and clean-clone verification on a machine with nothing cached.
- **Next step:** [going-live §F](../runbooks/going-live.md#f--ticket-039--clean-clone-verification).
- **Found:** 2026-09-27, ticket 080.

### TD-007 — The demo guard compares against a retired secret

- **Where:** `.github/workflows/demo-guard.yml` reads the real database URL from
  `secrets.BACKUP_DATABASE_URL`, a secret introduced for the R2 backup job. ADR 0008 retired
  that job and says "no repository secrets"; the backup now reads `BACKUP_DATABASE_URL` from
  `.env`, not from GitHub.
- **Why it matters:** the isolation step skips whenever either secret is unset, and says so
  only as a notice. Once 037 sets `DEMO_DATABASE_URL`, a missing real-URL secret leaves the
  most security-sensitive guard in the project green and doing nothing.
- **Next step:** a decision, then a small plan — keep one repository secret whose only job
  is this comparison (and rename it to say so), or compare something that needs no secret.
  Either way, fail rather than skip once `DEMO_DATABASE_URL` is set.
- **Found:** 2026-09-27, ticket 080.

### TD-008 — 060 waits on a decision

- **Where:** [060](active/060-seeding-a-cards-perks-from-a-catalogue.md), `todo — needs a
  decision`. The question: is seeding a card's perks from a public catalogue worth a network
  dependency, a mapping layer and a class of silently-wrong data, to save five minutes of
  typing per card in a two-card household? The plan's own read is *not yet*.
- **Next step:** the owner decides. If no, close it with the reasoning kept, as 045 and 046
  were.
- **Found:** 2026-09-27, ticket 080.

### TD-009 — Passkey leftovers in dependencies and config

- **Where:** `webauthn>=2.5` in `api/pyproject.toml` (nothing imports it since 047b), and
  `RP_ID = "allofmymoney.com"` in `fly.demo-api.toml` (nothing reads it).
- **Why it matters:** an unused dependency is attack surface and install time; dead config
  invites someone to believe it does something.
- **Next step:** remove both in one small plan; `uv lock` will change.
- **Found:** 2026-09-27, ticket 080.

### TD-010 — The series' staleness signal is served and never drawn

- **Where:** `NetWorthPoint.stale_account_count` (added in 014 at 027's request, "the chart
  wiring is 038"). No component reads it; only the MSW fixtures mention it.
- **Why it matters:** a stretch of the net worth chart built from a balance carried forward
  for months is drawn exactly like a measured one — the quiet wrongness
  [snapshots-and-carry-forward.md](../design-docs/snapshots-and-carry-forward.md#known-gap)
  exists to prevent.
- **Next step:** a frontend plan marking stale points on `charts/net-worth-chart.tsx`.
- **Found:** 2026-09-27, ticket 080.

### TD-011 — `AccountList` totals sum across kinds

- **Where:** `routers/accounts.py` computes `AccountList.total_cents` and
  `adjusted_total_cents` by adding every group — a mortgage plus a brokerage, liabilities
  added rather than subtracted. Ticket 029 noticed and chose not to render them.
- **Why it matters:** a response field that means nothing will eventually be displayed by
  someone who trusts the contract.
- **Next step:** remove both in a contract change (`make types`), or redefine them as net
  worth by delegating to `services/net_worth`.
- **Found:** 2026-09-27, ticket 080 (from 029).

### TD-012 — `SourceAdapter` was specified and never built

- **Where:** [account-sources.md](../design-docs/account-sources.md#the-sourceadapter-interface).
  The `DataSource` docstring in `models/enums.py` — compiled into `api-types.ts` — still
  says connectors plug in "behind the SourceAdapter interface".
- **Next step:** 075 Phase 1 builds it. Nothing to do before then.
- **Found:** 2026-09-27, ticket 080.

### TD-013 — An order-sensitive series test is flaky

- **Where:** `api/tests/test_net_worth_series.py::test_the_series_agrees_on_contributions_too`
  compares contribution lists in order, and neither `net_worth()` nor `net_worth_series()`
  orders its contributions. Which order Postgres returns depends on whether the planner picks
  a sequential or an index scan, which depends on the test database's statistics.
- **Seen:** failed once on 2026-09-27 on a docs-only commit (same four contributions, account
  215 moved from last to first), passed on every rerun.
- **Next step:** compare sorted by `account_id`, or give contributions a defined order in
  the service. The first is test-only; the second changes a response order.
- **Found:** 2026-09-27, ticket 080.

### TD-014 — Done plans with unticked acceptance boxes

- **Where:** 068–074 and 076–079 are `Status: done` with every acceptance box still `[ ]`.
  Their "Done" sections and commits say the work shipped.
- **Why it matters:** an agent reading a plan cannot tell a finished criterion from a
  skipped one. The exec-plan check does not flag this, because the boxes are history.
- **Next step:** tick them only after checking each against the code — not in bulk.
- **Found:** 2026-09-27, ticket 080.

### TD-015 — The stub ratchet is dormant

- **Where:** `api/app/routers/_stub.py` has no callers, and
  `test_contract.py::test_every_stub_returns_501` parametrises over nothing, because every
  declared route is live.
- **Next step:** keep it for the next contract-first plan (075's phases could declare their
  routes as stubs first), or delete both. Decide when 075 is cut.
- **Found:** 2026-09-27, ticket 080.

## Closed

None yet.
