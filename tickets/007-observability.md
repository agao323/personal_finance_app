# 007 — Observability: structured logs and error tracking
Status: done
Wave: 0   Lane: —
Blocked by: 006
Read first: docs/ARCHITECTURE.md#operations, docs/SECURITY.md#handling-real-data-during-development

## Goal
Structured JSON logging with request context on the API, Sentry on both services, and a
redaction filter that keeps financial values out of logs.

## Acceptance criteria
- [x] structlog JSON logging with request id, method, path, status, and duration on every request
- [x] Request id generated per request and returned in a response header
- [x] **Redaction filter**: any log field named like a monetary value (`balance`, `amount`, `total`, `net_worth`, ...) is replaced before emission
- [x] Sentry in `api/` and `web/`, DSN from env, cleanly disabled when unset
- [x] Sentry configured to scrub request bodies — no financial payloads leave the app
- [x] Unhandled exceptions produce one structured log line and one Sentry event
- [x] Tests: unit for the redaction filter across nested dicts and lists; functional asserting a 500 emits exactly one log line carrying the request id and no monetary value

## Files
- `api/app/logging.py`
- `api/app/middleware.py`
- `api/app/main.py`
- `web/src/lib/sentry.ts`
- `api/tests/test_logging.py`

## Notes
Redaction is the point of this ticket. Structured logs are useless if reading them means
reading your own balances out of a log aggregator — and Sentry breadcrumbs are the sneakiest
version of that leak.

Landing this before the first deploy means production has usable logs from its first request.
