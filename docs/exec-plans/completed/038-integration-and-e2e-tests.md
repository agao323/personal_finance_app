# 038 — Integration and E2E smoke tests
Status: done
Wave: 4   Lane: —
Blocked by: 027, 030, 032, 033, 037
Read first: docs/ARCHITECTURE.md#testing

## Goal
The tests that prove the three lanes actually joined up, and that nothing was left stubbed.

## Acceptance criteria
- [x] Playwright smoke test loading the dashboard against the synthetic seed, asserting net worth, runway, and the chart render
- [x] Playwright smoke test walking the CSV import wizard end to end
- [x] An integration test exercising seed → CSV import → apply rules → net worth against a real database
- [x] An integration test asserting a manual category override survives a rules re-run, end to end
- [x] **A test asserting no route returns 501** — every stub from 012 is implemented
- [x] All of the above running in CI against the compose stack
- [x] Tests: this ticket is the tests

## Files
- `web/e2e/dashboard.spec.ts`
- `web/e2e/import.spec.ts`
- `api/tests/test_integration.py`
- `.github/workflows/ci.yml`

## Notes
The no-501 assertion is the completeness check for the whole contract-first approach: 012
declared the full surface, and this proves every lane actually filled its share of it. It is
the cheapest possible guard against a route that everyone assumed the other lane built.

## Done — 2026-08-18

**No route returns 501.** Ticket 012 declared 33 operations and stubbed them; every one
is now implemented. That assertion walks the live app rather than a list, so it cannot
drift.

**The E2E run holds a real passkey.** The app is behind authentication as of 035, so
the browser has to actually sign in — Chrome's CDP WebAuthn virtual authenticator
answers the genuine ceremony, which means these tests exercise 034 and 035 rather than
routing around them. Registration happens once in a setup project and the session is
reused: the API's bootstrap window closes the moment the first credential exists, so a
per-test registration would be refused, correctly, and every test after the first would
fail for the wrong reason.

`make seed` now clears `credentials` and `webauthn_challenges`. Reseeding is a "reset
this database" action, and a synthetic database carrying a real authenticator's
credential is a confusing half-state — it is also what makes the run repeatable.

**The E2E assertions are shapes, not figures.** The seed is deterministic but its
snapshots are generated relative to today, so pinning `$692,793.29` would fail every
month for a reason unrelated to the code.

Three findings worth keeping:

- The API container image predated the `webauthn` dependency and crashed on import.
  `docker compose restart` does not rebuild; `make dev` and the new `make e2e` do.
- Two Playwright locators were ambiguous — "Net worth" matches the tile *and* the chart
  heading, "Skipped" matches the row badge *and* the file summary. Both were my
  specs, not the app.
- CI runs E2E as a separate job depending on the main one: it needs the whole compose
  stack rather than a Postgres service container, and a browser download should not
  slow the run most pushes care about.

### Not done

The demo deployment (037) is not built, so nothing here runs against it. Nothing in
this ticket needed it — the blocker was nominal.
