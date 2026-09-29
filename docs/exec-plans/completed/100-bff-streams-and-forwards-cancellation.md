# 100 — The BFF proxy streams without buffering, and forwards cancellation
Status: done
Wave: 10   Lane: W
Touches: none
Blocked by: 081
Integrates with: 099
Read first: docs/ADVISOR.md#request-path, docs/ARCHITECTURE.md#request-path

## Goal
An event the API writes reaches the browser when it is written, and a browser that goes away
stops the API's work — through `route.ts`, Next's server, and the deploy-shaped stack.

## Acceptance criteria
- [x] `route.ts` passes `signal: request.signal` to the upstream `fetch`. Today it does not, so a
      closed tab leaves the API running and spending.
- [x] Upstream `content-type: text/event-stream` and `cache-control` pass through unchanged.
- [x] `make smoke` gains a step: `curl -N` on `/api/advisor/stream-check` through web receives the
      first heartbeat within 1.5 s and the three at roughly one-second spacing. If Next's
      compression buffers it, set `compress: false` in `next.config.ts` — Cloudflare compresses at
      the edge anyway — and say so in a comment.
- [x] Tests: aborting the incoming request aborts the upstream fetch; chunks from a mock upstream
      that writes with delays arrive incrementally, not all at the end.

## Files
- `web/src/app/api/[...path]/route.ts`
- `web/src/app/api/[...path]/route.test.ts` (new)
- `web/next.config.ts` (only if compression buffers)
- `Makefile`

## Notes
The proxy already returns `upstream.body` as a stream, so this is a small change. The point of the
ticket is proving it through the real hops rather than assuming it. Cloudflare's own behaviour can
only be checked in production; that check is in 107's runbook.

Read the Next.js docs in `web/node_modules/next/dist/docs/` before touching `route.ts` —
`web/AGENTS.md` warns this version differs from what you remember.

## Done — 2026-09-28

- `route.ts` passes `signal: request.signal` upstream. The test aborts the browser's request and
  checks the upstream fetch's signal went with it.
- The incremental-delivery test holds the upstream open and reads the proxied body chunk by
  chunk; a buffering proxy would never resolve the first read.
- `make smoke` gains two steps: `alembic upgrade head` in the api container (what Fly's release
  command runs — the advisor routes need 0007), then `scripts/check_stream_timing.py`, which reads
  the stream check through web **asking for gzip, as a browser does**, and fails unless the first
  heartbeat lands within 1.5 s and the three are spread out.
- Run against the deploy-shaped stack in an isolated compose project: heartbeats at 0.07 s,
  1.08 s, 2.08 s, uncompressed. Next does not compress this response (`no-transform`), so
  `next.config.ts` is unchanged. Cloudflare's behaviour is checked in production, in 107's
  runbook.
