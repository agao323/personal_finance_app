# 038 — Integration and E2E smoke tests
Status: todo
Wave: 4   Lane: —
Blocked by: 027, 030, 032, 033, 037
Read first: docs/ARCHITECTURE.md#testing

## Goal
The tests that prove the three lanes actually joined up, and that nothing was left stubbed.

## Acceptance criteria
- [ ] Playwright smoke test loading the dashboard against the synthetic seed, asserting net worth, runway, and the chart render
- [ ] Playwright smoke test walking the CSV import wizard end to end
- [ ] An integration test exercising seed → CSV import → apply rules → net worth against a real database
- [ ] An integration test asserting a manual category override survives a rules re-run, end to end
- [ ] **A test asserting no route returns 501** — every stub from 012 is implemented
- [ ] All of the above running in CI against the compose stack
- [ ] Tests: this ticket is the tests

## Files
- `web/e2e/dashboard.spec.ts`
- `web/e2e/import.spec.ts`
- `api/tests/test_integration.py`
- `.github/workflows/ci.yml`

## Notes
The no-501 assertion is the completeness check for the whole contract-first approach: 012
declared the full surface, and this proves every lane actually filled its share of it. It is
the cheapest possible guard against a route that everyone assumed the other lane built.
