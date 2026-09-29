# Plans

Every change to this repo belongs to a plan: a numbered markdown file with a status and
acceptance criteria. Plans are what make a session resumable — an agent cannot see its own
usage budget, so progress has to live on disk ([DECISIONS.md](DECISIONS.md), "Workflow:
ticketed sessions, contracts first"). "Plan" and "ticket" mean the same thing here; the
files predate the folder name.

| Where | What |
|---|---|
| [exec-plans/active/](exec-plans/active/) | `todo`, `in-progress`, `planning` |
| [exec-plans/completed/](exec-plans/completed/) | `done`, `closed` — filenames and IDs never change, because commits and code comments cite them |
| [generated/exec-plans.md](generated/exec-plans.md) | The index of both, generated from the headers by `make docs` |
| [exec-plans/tech-debt-tracker.md](exec-plans/tech-debt-tracker.md) | Known debt that is not a plan yet |

## How to work a plan

1. Take the lowest-numbered plan with `Status: todo` in `exec-plans/active/` **in your
   lane**. Check its **Blocked by** field — a blocker in another lane means pick a
   different plan, not wait.
2. Read the plan. Read **only** the docs listed under **Read first** — context is the
   scarce resource, don't load the whole `docs/` tree.
3. Implement exactly the plan's scope. If you discover adjacent work, **add a new plan**
   with the next free number in `exec-plans/active/`; do not expand the current one. Debt
   too small to plan goes in the tech-debt tracker.
4. Run `make lint && make test && make types-check`. All must pass. CI runs the same.
5. Commit as `<id>: <imperative summary>`. Set `Status: done`, `git mv` the file to
   `exec-plans/completed/`, run `make docs` to refresh the generated index, and commit
   that too.

The one exception to "every change belongs to a plan" is the weekly
[doc-gardening](runbooks/doc-gardening.md) run: it only corrects docs to match the code, one
small PR per drift topic, and commits as `garden: <imperative summary>`.

If a plan turns out to be bigger than its scope suggests, stop and split it into
`NNNa` / `NNNb` rather than pushing through. An oversized plan is the main way a session
runs out of budget mid-change and leaves the repo broken.

Migrations are always reviewed by a human before merge — never `--autogenerate` and commit
blind — and only one in-flight plan may add one at a time. Alembic's revision chain is
linear; two concurrent migrations produce a branched head that has to be merged by hand.

## Plan format

```markdown
# NNN — Title
Status: todo | in-progress | planning | done | closed
Wave: N   Lane: A | B | C | —
Blocked by: NNN, NNN (or none)          ← hard prerequisite, must be done first
Integrates with: NNN, NNN (optional)    ← serves this plan's data; NOT a blocker
Read first: docs/FILE.md#anchor

## Goal
One paragraph. What exists after this that didn't before.

## Acceptance criteria
- [ ] Checkable, specific, testable
- [ ] Tests: what the unit and functional tests must cover

## Files
Expected files created/changed. A guide, not a contract — but >5 means split the plan.

## Notes
Gotchas, prior decisions that constrain the approach.
```

A status may carry a note after an em dash — `todo — needs a decision, see below`,
`closed — superseded by 047b`. `planning` means the file is a plan to be cut into
implementation plans when picked up, not an implementation (075 is the example). **Read
first** is required on active plans; `none` is a valid answer. The folder a plan sits in
must match its status, and `make test` checks both.

## Waves

| Wave | Plans | Mode | Outcome |
|---|---|---|---|
| 0 — Foundations | 001–008 | serial | Runs in Docker, CI green, contract pipeline works, **skeleton live on the internet** |
| 1 — Freeze | 009–012 | serial | Whole schema in one migration, ownership + snapshot services, API contract frozen |
| 2 — Build | 013–033, 040 | **3 lanes** | Every feature. 040 is a later Lane B fix to the seed |
| 3 — Auth & ship | 034–037 | serial | Passkeys, Access, origin lock, public demo |
| 4 — Close | 038–039 | serial | E2E green, README and ADRs |
| 5 — Account, then simplify | 041–047b | serial | Sign out, manage passkeys, add a partner, recover a lockout — then **remove the passkey layer**; Access is the authentication |
| 6 — Load time and perks | 048–052 | serial | The 5.5 s cold start, card perks v1 (schema, API, screen), the net worth series N+1 |
| 7 — Cards | 053–079, except 075 | **053 → 054 → 5 lanes**, then serial follow-ups | Multiple cards, editing, cadence-aware urgency, history, net value; then the master–detail rebuild and the period grid |
| 8 — Connectors | 075 | planning | SimpleFIN: transactions nightly, credits marked from them |
| 9 — Harness | 080 | serial | The repo as system of record: a map, a docs tree, checks that keep it true |
| 9 — Advisor foundations | 081–094, 122 | **081 → 082 → 083, then 3 lanes** | Tools, analyses, findings, and an Insights panel. **No model, no egress.** Plan: 122 |
| 10 — Advisor loop and chat | 095–107, 120, 121 | **2 lanes**, then 107 | Loop, audit, caps, grounding, evals, streaming chat — built on a free local model (120). Ships **switched off**; 107 switches it on behind gates, and is the first thing that costs money |
| 11 — Goals | 108–111 | serial | Spending limits, emergency fund, savings targets; stated assumptions; goal-aware advice |
| 12 — Debt and projections | 112–118 | 112 → 113, then fan-out | Liability terms, tax treatment, allocation, debt strategies, projections to the FIRE bar |
| 13 — Monthly review | 119 | serial | User-initiated, in-app only |

Wave 9 ran as two streams at once, on separate branches cut from the same commit: the harness
(080) and the advisor's foundations. They share the number because each was planned as "the
next wave"; the advisor's plan was written as 080 too and became **122** when the branches
met. Waves 11 and 12 were ordered provisionally, to be re-ranked by the advisor's
`note_limitation` counts; [ADVISOR.md](ADVISOR.md) has the design.

Ranges follow what each plan's header says. An earlier version of this table filed
045–047 as a separate "Wave 6 — Simplify"; the headers put them in Wave 5 and 048–052 in
Wave 6, and the headers were written at the time. There is no plan file for 065 — commit
`1c05117` ("065: tighten the cards UI after review") landed without one. The generated
index counts plans and lists gaps, so no count is hand-kept here.

Wave 7 rebuilds the cards page. Two serial plans then a five-way fan-out: **053** carries
the single migration the wave needs (partial redemption amounts, annual fee) plus the urgency
rule, **054** lands every endpoint, and then **055–059 are frontend-only and parallel** — each
owns one component file under `web/src/components/cards/`, with 055 landing `page.tsx` and the
slots the others fill.

Three decisions were taken up front rather than discovered: a redemption carries an **optional**
amount so one tap still means "fully used"; urgency thresholds are **fixed per cadence** (7 / 14 /
21 / 30 days) rather than configurable, because 30 days is noise on a monthly credit and too late
on an annual one; and a card's annual fee is stored so the page can answer the question perk
tracking actually serves — keep this card or cancel it.

The second half of Wave 5 undoes a decision rather than adding a feature. Ticket 044 made a
Cloudflare Access assertion sufficient to register a passkey on any device, which left the
passkey layer unable to refuse anyone Access admitted — a second factor the first factor
could re-issue. [ADR 0007](adr/0007-drop-passkeys.md) has the threat-by-threat reasoning.
045 and 046 are kept as superseded rather than deleted: they are the record of what the
removed subsystem was costing.

Wave 1 is what makes Wave 2 parallel. Ticket 009 puts the entire v1 schema in one
hand-reviewed migration, because Alembic's revision chain is linear and cannot absorb
concurrent branches. Ticket 012 declares every Pydantic model and every route — stubbed at
`501` — and generates `api-types.ts` from them, so frontend and backend are typed against the
same frozen file and cannot drift.

## Wave 2 lanes

| Lane | Theme | Plans | Owns |
|---|---|---|---|
| **A** | Aggregates & durability | 013–017 | `api/app/services/{net_worth,spend,runway}.py`, `api/app/routers/{net_worth,spend,runway,export}.py`, `api/scripts/backup.py` (replaced by `export_local.py` / `restore_local.py` in 017) |
| **B** | Accounts & ingestion | 018–024 | `api/app/services/{csv_import,categorize,sheet_import}.py`, `api/app/routers/{accounts,import_csv,rules,transactions}.py`, `api/scripts/{seed_synthetic,import_sheet_history}.py` |
| **C** | Frontend | 025–033 | all of `web/` |

Lane C is the critical path at nine plans. If a fourth lane is ever wanted, split Lane C
after 025 (the app shell) lands — everything after it is separate page files.

### Rules that make parallel lanes safe

- **One worktree per lane, one branch per plan.** CI runs on every branch, not just `main`.
- **A lane only edits files it owns.** The table above is the contract. If a plan needs a
  file another lane owns, it is scoped wrong — split it or move it.
- **Only plans 012 and 038–039 may edit `web/src/lib/api-types.ts`** during Wave 2. A Wave 2
  plan that needs a response-shape change **stops**, gets the change made in a re-freeze
  commit, and resumes. Do not hand-edit the generated file, ever. From Wave 3 on there is
  one worker and a plan changes the contract directly — run `make types` and commit the
  result ([ADR 0006](adr/0006-contract-changes-during-wave-2.md)).
- **Only one in-flight plan may add an Alembic migration.** After 009 this should be rare;
  if two lanes both need schema changes, they serialise.
- **Merge to `main` frequently.** A lane that runs five plans deep before merging will
  conflict on `Makefile`, `pyproject.toml`, and route registration.
- **`current_user` is a frozen dependency from 012.** Wave 2 gets the single configured user;
  ticket 034 replaces the implementation without touching the signature (and 047a replaced
  it again, the same way). No Wave 2 plan should know that auth doesn't exist yet.

### Lane C does not wait for Lanes A and B

This is the payoff of ticket 012 and it is easy to accidentally give up.

A frontend plan's **`Blocked by`** lists only its within-lane prerequisites. Its
**`Integrates with`** field names the backend plans serving its data — that is *not* a
blocker. Lane C builds against MSW mocks typed from `api-types.ts`, so the response shapes are
generated from the same Pydantic models the backend is implementing against. A shape mismatch
is impossible by construction.

What mocks can't catch is semantic mismatch — an endpoint returning `[]` where the component
assumed `null`, or a sparser series than the chart expected. That's what ticket 038 is for.
Point a screen at its real endpoint as soon as that endpoint lands; don't hold the plan for it.

If Lane C ever *does* block on Lane A or B, the lane structure has collapsed into a serial
plan wearing a table.

## Waves 9 and 10: the advisor's lanes

The Wave 2 pattern again, for the same reason: **081 freezes the contract** — every Insights and
advisor route stubbed at `501`, every model and the SSE event union generated into
`api-types.ts` — so the web lane builds against MSW while the API is still being written. 082
(read models out of routers) and 083 (the tool framework) complete the serial start.

| Lane | Theme | Plans | Owns |
|---|---|---|---|
| **T** | Tools | 084–086 | `api/app/advisor/tools/{balances,spending,cards}.py` |
| **S** | Analyses and findings | 087–093 | `api/app/services/analysis/**` (after 083's `periods.py`), `api/app/services/findings.py`, `api/app/advisor/tools/analysis.py`, `api/app/routers/insights.py` |
| **L** | Loop | 095–099, 101–103, 120 | `api/app/advisor/{model,model_local,pricing,loop,store,grounding,answer,sse}.py`, `advisor/prompts/`, `advisor/tools/meta.py`, `models/advisor.py`, `routers/advisor.py`, `api/evals/**`, migration 0007 |
| **W** | Web | 094, 100, 104–106 | `web/src/components/{insights,advisor}/**`, `web/src/app/(dashboard)/advisor/**`, `web/src/lib/{screens,advisor-stream,markdown-lite}.ts`, and `route.ts` for 100 |

- **Lane W starts the day 081 merges**, in Wave 9. Its `Integrates with` fields name the API
  plans that serve its data; they are not blockers.
- **Only 081, 095's re-freeze, and the Wave 11–12 schema plans edit `api-types.ts`.**
  Anything else needing a shape change stops and re-freezes, per ADR 0006.
- **Migrations serialise: 095 → 108 → 109 → 112 → 113 → 119.** One in flight at a time.
- Lane L's evals (101) depend on lanes T and S having landed their tools. That is the one
  cross-lane blocker, and it is at the end of the lane rather than the start.

**Header addition from Wave 9 on:** a `Touches:` line names a **migration**, a **contract**
change, or a **dependency**, so the serialising rules above can be checked at a glance.

## Tests

**Every plan ships unit and functional tests.** This is a standing rule, not repeated in
each plan's acceptance criteria unless there's something specific to say.

| Layer | Unit | Functional |
|---|---|---|
| Backend | pure service functions, hand-computed expected values | httpx against the app + a migrated test database |
| Frontend | vitest — formatters, hooks, query builders | Testing Library + MSW mocks typed from `api-types.ts` |

- Backend tests are `pytest`, colocated in `api/tests/`, one file per module under test.
- The test database is created by fixture and migrated with `alembic upgrade head`. **Never
  `metadata.create_all()`** — tests and production would drift and a broken migration would
  ship green. Never SQLite, for the same reason.
- Per-test transactional rollback, so the suite stays fast. It hides commit behaviour by
  construction, which is why `tests/test_db.py` tests the real session dependency
  separately ([ADR 0005](adr/0005-request-scoped-transactions.md)).
- Coverage is reported in CI and **not gated on a percentage**. Coverage gates get satisfied
  by tests that assert nothing.
- Playwright is for the two E2E smoke tests in 038 only (plus the opt-in screenshot capture).
- **Fixtures are always synthetic.** No test anywhere contains a real balance.
- A guard is tested like code: each one runs against a violating fixture (must fail) and a
  clean one (must pass). One that never fires looks exactly like one that is broken.

## Definition of done for v1

The Google Sheet is no longer being updated. That's the test.
