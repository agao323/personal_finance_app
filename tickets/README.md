# Tickets

44 tickets in six waves. Waves 0, 1, 3, and 4 are serial. **Wave 2 runs in three parallel
lanes.**

## How to work a ticket

1. Take the lowest-numbered ticket with `Status: todo` **in your lane**. Check its
   **Blocked by** field — a blocker in another lane means pick a different ticket, not wait.
2. Read the ticket. Read **only** the `docs/` files listed under **Read first** — context is
   the scarce resource, don't load the whole `docs/` tree.
3. Implement exactly the ticket's scope. If you discover adjacent work, **add a new ticket**
   at the end of the file list; do not expand the current one.
4. Run `make lint && make test`. Both must pass.
5. Commit as `<id>: <imperative summary>`. Set `Status: done` and commit that too.

If a ticket turns out to be bigger than its scope suggests, stop and split it into
`NNNa` / `NNNb` rather than pushing through. An oversized ticket is the main way a session
runs out of budget mid-change and leaves the repo broken.

## Waves

| Wave | Tickets | Mode | Outcome |
|---|---|---|---|
| 0 — Foundations | 001–008 | serial | Runs in Docker, CI green, contract pipeline works, **skeleton live on the internet** |
| 1 — Freeze | 009–012 | serial | Whole schema in one migration, ownership + snapshot services, API contract frozen |
| 2 — Build | 013–033 | **3 lanes** | Every feature |
| 3 — Auth & ship | 034–037 | serial | Passkeys, Access, origin lock, public demo |
| 4 — Close | 038–039 | serial | E2E green, README and ADRs |
| 5 — Account | 041–044 | serial | Sign out, manage passkeys, add a partner, recover a lockout |

Wave 1 is what makes Wave 2 parallel. Ticket 009 puts the entire v1 schema in one
hand-reviewed migration, because Alembic's revision chain is linear and cannot absorb
concurrent branches. Ticket 012 declares every Pydantic model and every route — stubbed at
`501` — and generates `api-types.ts` from them, so frontend and backend are typed against the
same frozen file and cannot drift.

## Wave 2 lanes

| Lane | Theme | Tickets | Owns |
|---|---|---|---|
| **A** | Aggregates & durability | 013–017 | `api/app/services/{net_worth,spend,runway}.py`, `api/app/routers/{net_worth,spend,runway,export}.py`, `api/scripts/backup.py` |
| **B** | Accounts & ingestion | 018–024 | `api/app/services/{csv_import,categorize,sheet_import}.py`, `api/app/routers/{accounts,import_csv,rules,transactions}.py`, `api/scripts/{seed_synthetic,import_sheet_history}.py` |
| **C** | Frontend | 025–033 | all of `web/` |

Lane C is the critical path at nine tickets. If a fourth lane is ever wanted, split Lane C
after 025 (the app shell) lands — everything after it is separate page files.

### Rules that make parallel lanes safe

- **One worktree per lane, one branch per ticket.** CI runs on every branch, not just `main`.
- **A lane only edits files it owns.** The table above is the contract. If a ticket needs a
  file another lane owns, it is scoped wrong — split it or move it.
- **Only tickets 012 and 038–039 may edit `web/src/lib/api-types.ts`.** A Wave 2 ticket that
  needs a response-shape change **stops**, gets the change made in a re-freeze commit, and
  resumes. Do not hand-edit the generated file, ever.
- **Only one in-flight ticket may add an Alembic migration.** After 009 this should be rare;
  if two lanes both need schema changes, they serialise.
- **Merge to `main` frequently.** A lane that runs five tickets deep before merging will
  conflict on `Makefile`, `pyproject.toml`, and route registration.
- **`current_user` is a frozen dependency from 012.** Wave 2 gets the single configured user;
  ticket 034 replaces the implementation without touching the signature. No Wave 2 ticket
  should know that auth doesn't exist yet.

### Lane C does not wait for Lanes A and B

This is the payoff of ticket 012 and it is easy to accidentally give up.

A frontend ticket's **`Blocked by`** lists only its within-lane prerequisites. Its
**`Integrates with`** field names the backend tickets serving its data — that is *not* a
blocker. Lane C builds against MSW mocks typed from `api-types.ts`, so the response shapes are
generated from the same Pydantic models the backend is implementing against. A shape mismatch
is impossible by construction.

What mocks can't catch is semantic mismatch — an endpoint returning `[]` where the component
assumed `null`, or a sparser series than the chart expected. That's what ticket 038 is for.
Point a screen at its real endpoint as soon as that endpoint lands; don't hold the ticket for it.

If Lane C ever *does* block on Lane A or B, the lane structure has collapsed into a serial
plan wearing a table.

## Tests

**Every ticket ships unit and functional tests.** This is a standing rule, not repeated in
each ticket's acceptance criteria unless there's something specific to say.

| Layer | Unit | Functional |
|---|---|---|
| Backend | pure service functions, hand-computed expected values | httpx against the app + a migrated test database |
| Frontend | vitest — formatters, hooks, query builders | Testing Library + MSW mocks typed from `api-types.ts` |

- The test database is created by fixture and migrated with `alembic upgrade head`. **Never
  `metadata.create_all()`** — tests and production would drift and a broken migration would
  ship green.
- Per-test transactional rollback, so the suite stays fast.
- Coverage is reported in CI and **not gated on a percentage**. Coverage gates get satisfied
  by tests that assert nothing.
- Playwright is for the two E2E smoke tests in 038 only.
- **Fixtures are always synthetic.** No test anywhere contains a real balance.

## Ticket format

```markdown
# NNN — Title
Status: todo | in-progress | done
Wave: N   Lane: A | B | C | —
Blocked by: NNN, NNN (or none)          ← hard prerequisite, must be done first
Integrates with: NNN, NNN (optional)    ← serves this ticket's data; NOT a blocker
Read first: docs/FILE.md#anchor

## Goal
One paragraph. What exists after this that didn't before.

## Acceptance criteria
- [ ] Checkable, specific, testable
- [ ] Tests: what the unit and functional tests must cover

## Files
Expected files created/changed. A guide, not a contract — but >5 means split the ticket.

## Notes
Gotchas, prior decisions that constrain the approach.
```

## Definition of done for v1

The Google Sheet is no longer being updated. That's the test.
