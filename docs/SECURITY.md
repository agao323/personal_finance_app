# Security

## Threat model

The app holds a complete financial picture of one household. Ranked by actual risk, which is
not the same as intuitive risk:

| # | Risk | Mitigation |
|---|---|---|
| 1 | Real data leaking into the public demo | Separate deployment, **separate Neon project**, synthetic seed. Infra boundary, not a flag. |
| 2 | Database and **backups** at rest | Neon encryption at rest; nightly `pg_dump` encrypted with a key stored outside Neon. |
| 3 | Secrets or real values in git history | `data/` gitignored; secret scanning in CI; no fixture ever contains a real number. |
| 4 | Real values leaking into logs or an AI session transcript | Log redaction filter with a test; `data/` never read into context. Advisor transcripts: Postgres, 30-day TTL ([ADR 0012](adr/0012-transcripts-live-in-postgres-for-30-days.md)). |
| 5 | AI agent exfiltration | See [AI agent](#ai-agent) and [ADVISOR.md](ADVISOR.md). The model half ships last, switched off. |
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

### The advisor's threat model

Planned in ticket 080; the design is [ADVISOR.md](ADVISOR.md). The feature splits in two, and
"ships last" now applies to the half that calls a model — see
[DECISIONS.md](DECISIONS.md#2026-09-27--the-ai-advisor-the-half-without-a-model-ships-first-the-half-with-one-still-ships-last).
The constraints above stand unchanged; these are the threats they are answering, ranked.

| # | Threat | Vector | Mitigation | Residual |
|---|---|---|---|---|
| 1 | **Confidently wrong numbers** | The model subtracts, rounds or recalls a figure itself | Figures computed in Python and rendered pre-formatted; a grounding check on every answer; findings computed deterministically ([ADR 0011](adr/0011-findings-are-computed-and-figures-are-grounded.md)) | A correct figure with a wrong explanation. The evals, not the checker, cover reasoning |
| 2 | **Injection steering advice** | Instructions in a merchant name, memo, perk note or account name — CSV today, SimpleFIN later | Untrusted text marked by field name and sanitised at the tool boundary; instruction-like text and tool names withheld; canary-tagged injection corpus in the evals | Persuasive wording can still colour an explanation. There is no action it can take |
| 3 | **Exfiltration through the browser** | A markdown image or link in an answer, fetched or clicked | Stripped by the API, not renderable by the chat (no `a`, no `img`), and blocked by CSP `img-src`/`connect-src 'self'` — three independent layers | None known |
| 4 | **Exfiltration through a tool** | A tool that reaches the network or writes | No fetch tool, no server tools, no write tools; each call in a `READ ONLY` transaction; the one free-text argument cannot express a URL; a test asserts the tool list sent is exactly the registry | — |
| 5 | **Advice on stale or partial data** | 90-day carry-forward; CSV freshness; history before the first snapshot | Staleness in every tool result; `data_health`; stale evidence demotes a finding and turns its action into "update this balance" | Data the app does not know is missing |
| 6 | **Denial of wallet** | Tool loops, long conversations, a leaked session | Per-turn, per-conversation and monthly caps checked before every call; a kill switch that defaults off; **a provider-side spend limit** that no bug here can bypass | Up to the monthly cap |
| 7 | **The provider reads household data** | Every tool result is sent to it | Minimisation — aggregates by default, bounded rows, no emails, names or institutions; 30-day deletion; no training by default; a dedicated workspace ([ADR 0009](adr/0009-advisor-model-provider.md)) | A fourth processor, with up to two years' retention if a request is flagged. Accepted consciously, or not at all |
| 8 | **Transcripts at rest** | Figures in prose in Postgres and in backups | 30-day TTL, immediate delete, and a delete confirmation that says backup files keep their copy | Copies in backups written before the delete |
| 9 | **Leaks through observability** | Stack-frame local variables in Sentry; arguments in logs | `include_local_variables=False`; stdout carries tool names and counts only; arguments go to the audit table, never stdout | — |
| 10 | **The public demo as a spend or prompt surface** | An unauthenticated endpoint that calls a model | The demo never calls one: disabled in code under `DEMO_MODE`, no key deployed, CI guard, recorded answers instead ([ADR 0014](adr/0014-the-demo-advisor-replays-recorded-answers.md)) | — |

Two things this does **not** change. The API still has no public address, and a model provider is
not reached by joining anything to Fly's private network — which is one reason self-hosting on a
laptop was rejected in ADR 0009. And the advisor cannot move money, because nothing in this app
can.

## Backups

- Neon's own automatic backups and point-in-time restore are layer one, and come free with
  the platform choice.
- Layer two is a **local** full export: `make backup` writes every table to
  `data/backups/`, which is gitignored, and the machine's own backup carries it from there.
  Nothing we operate stores a copy offsite — see [ADR 0008](adr/0008-local-backups.md),
  which supersedes the encrypted-dumps-to-R2 design in [0004](adr/0004-backups.md).
- **Restore is tested at least once** before the app is trusted with real data. An untested
  export is a file you believe in. **No real data enters production until ticket 017 is
  done** — the Google Sheet import runs against a local database until then.
- Full data export from the UI (`GET /export`). The app must never become a place data can
  only go into — that's both a user-hostile design and insurance against losing interest in
  the project.
- **Only `balance_snapshots` is genuinely irreplaceable.** Banks do not serve historical
  balance-at-a-date, and for 401k, HSA, brokerage, property and vehicle values nobody does.
  Everything else is bank CSVs inside their retention window or a handful of hand-typed
  rows. Knowing which rows actually cannot be rebuilt is what made layer two small enough
  to be worth having.

This matters more than it looks: moving a financial picture out of Google Sheets (which
Google backs up) into a self-operated database is a real downgrade in durability until
backups are proven. It is also the reason Neon won over a self-run Postgres VM — see
[ARCHITECTURE.md](ARCHITECTURE.md#hosting).
