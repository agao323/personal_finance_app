# 006 — CI pipeline
Status: done
Wave: 0   Lane: —
Blocked by: 005
Read first: docs/ARCHITECTURE.md#testing

## Goal
GitHub Actions runs lint, typecheck, and tests for both sides on every push to every branch,
plus the contract drift check, a secret scan, and the architectural guard checks.

## Acceptance criteria
- [x] Workflow runs `make lint` and `make test` on **every branch**, not just `main`
- [x] Postgres service container for backend tests
- [x] Contract drift check: `make types`, then fail if the working tree is dirty
- [x] Secret scanning step (gitleaks or equivalent)
- [x] A check that fails if `Float` appears in a SQLAlchemy column definition
- [x] A check that fails if `NEXT_PUBLIC_API_URL` or an absolute API origin appears anywhere in `web/`
- [x] Coverage reported for both suites; **no percentage gate**
- [x] CI green on `main`
- [x] Tests: each guard script has a fixture proving it **fails** on a violating input and passes on a clean one — a guard that never fires is indistinguishable from a broken guard

## Files
- `.github/workflows/ci.yml`
- `scripts/check_no_float.sh`
- `scripts/check_no_public_api_url.sh`

## Notes
Running on every branch is what makes Wave 2's three lanes safe — a lane finds out it broke
`main`'s contract before the merge, not after.

The float check sounds fussy. It is the cheapest possible guard against the one bug class
that silently corrupts financial data.
