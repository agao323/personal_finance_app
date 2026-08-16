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

Two independent layers on the real deployment:

1. **Cloudflare Access** in front of `app.<domain>`. Identity enforced at the edge — requests
   from unauthorized identities never reach the origin. Zero auth code in the request path.
2. **Passkeys (WebAuthn)** implemented in the application, with the `users` table as a hard
   allowlist. Phishing-resistant.

Layer 1 is the security. Layer 2 is real, exercised by the production app and its test suite,
and is the part that's worth understanding and building.

**No password auth. Ever.** There is no version of hand-rolled password auth worth the time,
and it is the most common way projects like this get owned. No recovery codes either — a lost
passkey is recovered by re-registering from behind Access, which is a stronger gate than any
recovery flow would be.

### Why the API has no public address

The browser never calls the API directly; Next.js proxies to it over Fly's private network.
Beyond the architectural reasons in [ARCHITECTURE.md](ARCHITECTURE.md#request-path), this
matters for security specifically: a Fly app is publicly addressable by default, so Cloudflare
Access in front of a reachable origin is a false sense of security. Here there is no second
hostname to forget to lock down.

The origin still validates the `Cf-Access-Jwt-Assertion` JWT — defense in depth, in case the
Fly app is ever given a public address by accident.

Session cookies are `httpOnly`, `secure`, `sameSite=lax`, host-scoped to the single origin.
`lax` rather than `strict` because the Access redirect returns the user cross-site.

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
