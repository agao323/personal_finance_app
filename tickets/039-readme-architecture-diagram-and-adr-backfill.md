# 039 — README, architecture diagram, and ADR backfill
Status: in-progress
Wave: 4   Lane: —
Blocked by: 038
Read first: docs/PRODUCT.md#craft-bar

## Goal
The documentation layer: what the repo tells someone who arrives with no context — including
future me. Not documentation debt.

## Acceptance criteria
- [x] README: what it is, screenshots, live demo link, local setup that works from a clean clone
- [x] Architecture diagram (Mermaid, rendered in the README) showing the BFF topology and the private API
- [x] Explicit trade-offs section: why FastAPI + Next.js, **why the API is private behind a BFF**, why not Kubernetes, why manual-first over aggregators, why the demo is a separate deployment, why one upfront migration, why effective-dated ownership
- [x] ADRs backfilled for decisions made during implementation
- [ ] Test and CI badges
- [ ] Clean-clone setup verified by following the README literally, on a machine with nothing cached
- [ ] Tests: none — but the clean-clone verification is the acceptance criterion and must actually be performed

## Files
- `README.md`
- `docs/adr/*.md`

## Notes
The clean-clone verification is the criterion with teeth. A README that drifted from reality
is worse than no README — it sends you debugging a setup that was never going to work. Do it
on a machine with nothing cached, and follow your own instructions literally rather than from
memory.

The trade-offs section is the one to write in your own voice. Every decision in it is already
argued in `docs/DECISIONS.md`; the point of restating them in the README is that in a year the
reasoning will have evaporated and only the conclusions will remain. Conclusions without
reasoning are how a settled question gets reopened.

## Status — 2026-08-18: written, two criteria outstanding

The README is rewritten: what it is, four screenshots captured from the running app
against the synthetic seed, a Mermaid diagram of the BFF topology, the full trade-offs
section, local setup, deploy steps, and the two dev-environment traps that each cost
twenty minutes to rediscover (a dependency needs a container rebuild; a new route
directory 404s until the web container restarts).

Screenshots are captured by `e2e/screenshots.spec.ts`, which is skipped unless
`CAPTURE_SCREENSHOTS=1` — it reuses the signed-in session and seeded database the E2E
run already sets up, so regenerating them is one command rather than a manual pass.

Two ADRs backfilled:

- **0005 — the request is the transaction boundary.** The missing-commit bug and, more
  usefully, why the test suite could not see it. A fixture that makes tests fast by
  removing a production behaviour hides bugs in exactly that behaviour.
- **0006 — re-freezing the contract four times.** Four additive contract changes across
  twenty-one Wave 2 tickets, each with the workaround that was rejected and why. Without
  this a later reader would read four re-freezes as sloppiness rather than procedure.

### Outstanding

- [ ] **Live demo link** — needs ticket 037, which needs a separate Neon project.
- [ ] **Test and CI badges** — the badge URL needs the real GitHub org and repo name.
      Add once the repo is pushed:
      `![CI](https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg)`
- [ ] **Clean-clone verification** — the criterion with teeth, and it must actually be
      performed on a machine with nothing cached. Every path, `make` target and doc link
      referenced in the README has been checked to exist, and the E2E suite exercises
      `make seed` plus the full stack on every run — but that is this machine, with a
      warm Docker cache and a populated pnpm store. It is not the same test.
