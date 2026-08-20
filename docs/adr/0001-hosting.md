# 0001 — Hosting: Fly.io, Neon, and a private API

Date: 2026-08-17
Status: accepted

## Context

The app is two services and a Postgres database, serving one household. It has to be
reachable on a real domain with TLS, hold a complete financial picture safely, and cost
close to nothing while idle. A public demo will later run the same images against a
separate database.

Two constraints shaped this more than anything else:

- **The API must have no public address.** That is what makes the origin lock
  structural rather than a policy someone could misconfigure, and it is why there is
  one Cloudflare Access application instead of two. See
  [ARCHITECTURE.md#request-path](../ARCHITECTURE.md#request-path).
- **Moving off Google Sheets is a durability downgrade until backups are proven.**
  Google was backing that data up. Whatever hosts Postgres has to be at least as
  trustworthy as a spreadsheet, from day one.

## Decision

**Fly.io for both services; Neon for Postgres; the API on Fly's private network only.**

- `fly.web.toml` declares an `[http_service]`. It is the sole public entry point.
- `fly.api.toml` declares **no** `[[services]]`, no `[http_service]`, and no `ports`.
  The web service reaches it at `http://pfa-api.internal:8000` over Fly's private
  IPv6 network.
- Migrations run as a Fly `release_command`, not on boot.
- Neon holds the database, using its **pooled** connection endpoint.

## Alternatives considered

**`.flycast` instead of `.internal` for the API.** Flycast routes private traffic
through the Fly proxy, which brings load balancing and — the real attraction —
autostart, so the API machine could sleep when idle and wake on demand. It lost on a
narrow but decisive point: flycast requires an `[http_service]` or `[[services]]`
block in the config. The moment that block exists, public exposure is one allocated IP
away, and the guarantee moves from *structurally impossible* to *correctly
configured*. Given the API is the thing holding the financial data, the couple of
dollars a month for an always-on machine is cheap insurance. Revisit if the API ever
needs more than one instance, at which point load balancing starts to matter.

**Fly Postgres.** Cheaper — roughly $2–3/month against Neon's free tier — but Fly's
classic Postgres is a VM you operate, not a managed service. Backups become entirely
our problem at exactly the moment the durability argument above says they must not be.
Neon's automatic backups plus the nightly `pg_dump` in ticket 017 gives two
independent layers for $0.

**Two Neon branches instead of two projects** for real and demo. Rejected: branches
share a project and an account, and the real/demo split is a trust boundary rather
than an environment split. Branching is the right tool for dev/prod convenience and
the wrong one here. Two free projects cost nothing.

**Migrations on application boot.** Simpler — no release command to configure — but
two machines starting simultaneously race the same migration. A release command runs
once, before the new version takes traffic, and a failure aborts the deploy instead of
half-migrating under live requests.

**Kubernetes.** Covered in
[ARCHITECTURE.md#why-not-kubernetes](../ARCHITECTURE.md#why-not-kubernetes). Wrong tool
by two orders of magnitude at one household of traffic.

## Amendments

### 2026-08-18 — TLS mode: Full (strict), not Automatic

Cloudflare sits in front of the web app, so it also terminates TLS and re-encrypts to
Fly. That leg is set to **Full (strict)** — Cloudflare validates Fly's certificate —
rather than Cloudflare's recommended **Automatic** mode.

On the happy path the two are identical: Automatic probes the origin, finds a valid
Let's Encrypt certificate, and selects Full (strict) itself. They differ only in what
happens when something breaks. Automatic exists to keep a site *up* by adapting
downward if the origin's certificate stops validating; Full (strict) fails closed.

For this app that trade runs the wrong way. The Cloudflare-to-Fly leg carries a
complete financial picture, and the difference between the settings is precisely
whether that leg can become unvalidated — or, at Flexible, unencrypted — without
anyone deciding it should. An app that breaks because a certificate lapsed is an
afternoon's annoyance noticed immediately. An app quietly serving over a weaker
channel for six weeks is not noticed at all.

This is the same shape as the two decisions above: the API has no public address
rather than a protected one, and demo isolation is a separate deployment rather than
a flag. Prefer the configuration that cannot silently degrade, and accept a louder
failure in exchange.

*Cost, accepted:* a failed certificate renewal takes the site down instead of
degrading it. Fly renews over HTTP-01, which Cloudflare's proxy can interfere with; if
`fly certs check` ever reports a renewal failure, `fly certs setup` switches to DNS
validation.

### 2026-08-18 — The app lives at the apex

The real app is `allofmymoney.com`; the demo will be `demo.allofmymoney.com`. The
earlier `app.` prefix was dropped — it is a distinction that means something only to
people who build web apps, and the apex is the name that gets said out loud.

Two consequences worth recording:

- ~~**The session cookie must stay host-only.**~~ ~~**The WebAuthn RP ID becomes
  `allofmymoney.com`.**~~ Both obsolete as of ticket 047b — this app sets no cookies and
  holds no credentials. See [ADR 0007](0007-drop-passkeys.md). The apex-versus-subdomain
  reasoning still applies to Cloudflare's own `CF_Authorization`, which Cloudflare scopes,
  and to the Access application itself: the demo is a **separate** Access-less deployment
  on `demo.`, which is why the apex choice cost nothing.

## Consequences

**Easy.** The API cannot be reached from the internet, so there is no origin to lock
down, no CORS, and one Access policy. Deploys are `make deploy-api` / `make deploy-web`.
Idle cost is close to zero because the web machine sleeps. Neon's free tier covers
both databases with room to spare.

**Hard.** Debugging the API in production means `fly ssh console` or reading logs —
there is no URL to curl from a laptop. That is the intended trade and it will
occasionally be annoying. `.internal` also means no Fly proxy in front of the API, so
its machine must stay running; autostop savings apply to the web service only.

**Foreclosed.** Scaling the API beyond one machine would need load balancing, which
`.internal` does not provide — that would mean revisiting flycast and re-examining the
guard in `scripts/check_fly_api_private.sh`. Not a concern at one household, and the
guard is the thing that would force the conversation rather than letting it happen
silently.

**Cost.** Roughly $2–5/month: one always-on shared-cpu-1x machine for the API, a
sleeping one for the web app, Neon and Cloudflare free, plus ~$12/year for the domain.
