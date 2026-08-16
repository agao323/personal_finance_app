# 039 — README, architecture diagram, and ADR backfill
Status: todo
Wave: 4   Lane: —
Blocked by: 038
Read first: docs/PRODUCT.md#craft-bar

## Goal
The documentation layer: what the repo tells someone who arrives with no context — including
future me. Not documentation debt.

## Acceptance criteria
- [ ] README: what it is, screenshots, live demo link, local setup that works from a clean clone
- [ ] Architecture diagram (Mermaid, rendered in the README) showing the BFF topology and the private API
- [ ] Explicit trade-offs section: why FastAPI + Next.js, **why the API is private behind a BFF**, why not Kubernetes, why manual-first over aggregators, why the demo is a separate deployment, why one upfront migration, why effective-dated ownership
- [ ] ADRs backfilled for decisions made during implementation
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
