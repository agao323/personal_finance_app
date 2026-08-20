# Security

## Threat model

The app holds a complete financial picture of one household. Ranked by actual risk, which is
not the same as intuitive risk:

| # | Risk | Mitigation |
|---|---|---|
| 1 | Real data leaking into the public demo | Separate deployment, **separate Neon project**, synthetic seed. Infra boundary, not a flag. |
| 2 | Database and **backups** at rest | Neon encryption at rest; nightly `pg_dump` encrypted with a key stored outside Neon. |
| 3 | Secrets or real values in git history | `data/` gitignored; secret scanning in CI; no fixture ever contains a real number. |
| 4 | Real values leaking into logs or an AI session transcript | Log redaction filter with a test; `data/` never read into context. |
| 5 | AI agent exfiltration | See [AI agent](#ai-agent). Ships last. |
| 6 | Session hijack / weak auth on the real app | Cloudflare Access at the edge + passkeys. No passwords, ever. |
| 7 | Aggregator holding bank credentials | Only relevant post-v1. Accepted consciously if a connector ships. |

**Traffic interception is not on this list** because TLS solves it and every host provides it
free. It's the intuitive worry and the least of the actual ones. Enforce HSTS and move on.

## Auth

**Cloudflare Access is the authentication. The `users` table is the authorisation.**

Identity is enforced at the edge — requests from unauthorised identities never reach the
origin, and there is zero auth code in the request path. The API then verifies the same
`Cf-Access-Jwt-Assertion` itself (signature, issuer, audience) and resolves the email to an
**active** row in `users`. Passing Access is necessary and not sufficient: an identity Access
authenticated but this household never added is refused.

Both halves matter. Without the `users` allowlist, an Access policy written one line too
broadly would be a total compromise rather than a refused request.

**This app holds no credential of its own.** No passwords, no passkeys, no session cookie, no
`SESSION_SECRET`. There is nothing here to steal, phish, or leak, and nothing to rotate.

### What was here before, and why it went

Until 2026-08-20 there was a second layer: passkeys in the application, described here as
"layer 1 is the security, layer 2 is real." Ticket 044 then made a valid Access assertion
sufficient to register a passkey on any device — the correct fix for a lockout, and the end of
the second layer's independence. It could no longer refuse anyone the first layer admitted.

Working the threats through, the only one it still covered was physical possession of an
already-authenticated device. [ADR 0007](adr/0007-drop-passkeys.md) has the full table, the
cost, and the conditions the removal was accepted on — which are part of the decision, not
follow-ups:

- The Google account carries a **hardware key or passkey**, not SMS or TOTP. It is now the
  entire perimeter and must be the strongest link.
- **Access session duration is 24 hours.** This is the mitigation for the threat given up.
- The `users` allowlist stays.
- Screen locks on every device.

Further defence in depth belongs **in Access** — device posture, WARP enrolment, a second
identity provider — where Cloudflare maintains it rather than this codebase.

### Signing out, and getting unstuck

The only session is Cloudflare's, so the only sign-out is `/cdn-cgi/access/logout` on this
hostname. Know that it fails when the Access organisation named in the cookie no longer
resolves — a renamed team, for instance — which is precisely when it is most needed. The
recovery for that is the origin clearing `CF_Authorization` itself on a failed assertion
(ticket 042), since the origin serves the same hostname the cookie is set on. That is now the
only in-browser way out of a stuck Access session, so it must not be removed.

### Locally, and on the demo

There is no Access in front of a laptop or the public demo, so absence of a check must never
read as a passing one:

- **Local development** names an identity in `DEV_IDENTITY_EMAIL`. It is ignored the moment
  the origin is https, and ignored whenever Access is configured.
- **The demo** serves a fixed synthetic identity, is a separate deployment against a separate
  Neon project, and refuses every mutating verb.
- **A deployed environment with Access unconfigured does not start at all.** Refusing each
  request would be correct and one request too late; an operator should learn from a failed
  release, not a support conversation.

### Why the API has no public address

The browser never calls the API directly; Next.js proxies to it over Fly's private network.
Beyond the architectural reasons in [ARCHITECTURE.md](ARCHITECTURE.md#request-path), this
matters for security specifically: a Fly app is publicly addressable by default, so Cloudflare
Access in front of a reachable origin is a false sense of security. Here there is no second
hostname to forget to lock down.

The origin still validates the `Cf-Access-Jwt-Assertion` JWT — defense in depth, in case the
Fly app is ever given a public address by accident.

This app sets no cookies of its own. The only one in play is Cloudflare's
`CF_Authorization`, which Cloudflare sets and scopes.

## Demo isolation

The rule: **demo mode is a deployment, not a feature flag.**

A runtime "scramble the numbers" flag over real data means one missed check — a forgotten
route, a cached response, a new endpoint — leaks a real financial picture to whoever was
sent the link. Given that the entire point of the demo is to send the link to strangers,
that's not an acceptable failure mode.

Enforced by:

- Separate Fly apps, **a separate Neon project**, separate credentials. The demo's
  `DATABASE_URL` cannot resolve the real database.
- Separate *projects*, not branches. Neon branches share a project and an account; that is a
  weaker boundary than separate credentials, and this is the one boundary that must not be
  weak.
- `DEMO_MODE=true` causes the API to reject all mutating verbs. This is defense in depth,
  *not* the boundary.
- The synthetic seed script refuses to run against a database whose `data_marker` row says
  the data is real.
- CI asserts the demo and real database URLs differ and belong to different Neon projects.

The demo is **read-only in v1.** Allowing writes against a synthetic database is safe in
principle — that's what the isolation boundary buys — but it adds a public, unauthenticated
write surface that needs rate limiting, and a reseed cron to keep it presentable. Noted as a
fast follow, not a v1 commitment.

The synthetic seed generates a *coherent* financial picture — correlated income and spend,
realistic category mix, plausible growth curves — plus a few deliberately interesting cases:
a 50%-owned rental property (exercises ownership math), a maxed 401k, a mid-history stake
change, a closed account, transfer pairs, and some uncategorised transactions. Seeded RNG, so
the demo is reproducible.

The demo deployment **omits authentication entirely, at build time** — the demo bundle must
not contain a code path capable of authenticating against the real API. The passkey
implementation is therefore exercised by the production app and by its test suite, not by the
demo.

## Handling real data during development

**Principle: code touches the data, context describes the data.**

When working with real financial files, write a script that processes them. Do not read real
values into an AI session's context in order to work with them. The distinction is concrete:
an import script parsing 500 rows is fine; pasting 500 rows into a prompt is not.

Practically:

- Real exports live in `data/`, which is gitignored. They never move anywhere else.
- Import scripts are written against the *header shape* and validated against synthetic
  fixtures.
- Schema design uses structure — sheet names, column headers, category lists — not values.
- Dev and test databases run on generated synthetic data. Only production holds real data.
- Logs redact financial values. There is a test for it.

Relevant platform facts (verify current settings; these change):

- On Claude consumer plans, training on chats and coding sessions is a setting you control at
  `claude.ai/settings/data-privacy-controls`. **Retention follows it: 5 years if enabled,
  30 days if not.** Turn it off for this project.
- Claude Code stores session transcripts locally in **plaintext** under `~/.claude/projects/`
  for 30 days by default (`cleanupPeriodDays` to change).
- `/feedback`, `/bug`, and `/share` upload conversation history including code, retained
  5 years. **Do not use them in this repo.**

## AI agent

The planned "ask questions about my finances" agent is the highest-risk feature in the
project. An LLM with read access to a complete financial picture plus any outbound capability
is an exfiltration path — and the injection doesn't have to come from the user. A transaction
memo, a merchant name, or a scraped page can carry instructions.

Constraints, non-negotiable, to be enforced when the feature is built:

- A **fixed set of read-only, parameterized query tools**. No model-generated SQL against the
  real database, ever.
- **No outbound fetch tool.** The model API is the only egress.
- **No write tools.** The agent cannot mutate state.
- Every tool call logged with arguments.
- Prefer returning aggregates over row-level data where the question allows it.

It ships **last**: highest risk, lowest marginal value, and much easier to add safely once
the data model is stable.

## Backups

- Neon's own automatic backups and point-in-time restore are layer one, and come free with
  the platform choice.
- Layer two is ours: automated nightly `pg_dump` to Cloudflare R2, encrypted with a key held
  outside Neon, retention 30 days.
- **A dead-man's-switch** (healthchecks.io or equivalent) alerts when the nightly job fails
  to check in. A backup job that silently stops working is worse than no backup, because it
  is trusted.
- **Restore is tested at least once**, into a scratch database, before the app is trusted
  with real data. An untested backup is not a backup. **No real data enters production until
  ticket 017 is done** — the Google Sheet import runs against a local database until then.
- Full data export from the UI (`GET /export`). The app must never become a place data can
  only go into — that's both a user-hostile design and insurance against losing interest in
  the project.

This matters more than it looks: moving a financial picture out of Google Sheets (which
Google backs up) into a self-operated database is a real downgrade in durability until
backups are proven. It is also the reason Neon won over a self-run Postgres VM — see
[ARCHITECTURE.md](ARCHITECTURE.md#hosting).
