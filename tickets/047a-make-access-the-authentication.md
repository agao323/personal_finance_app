# 047a — Make Cloudflare Access the authentication
Status: todo
Wave: 5   Lane: —
Blocked by: none
Read first: docs/adr/0007-drop-passkeys.md

## Goal
`current_user` resolves an identity from the Cloudflare Access assertion instead of a
session cookie. Nothing is deleted yet.

## Why this is split from 047b

This half is the one that can be **silently wrong**. Every failure mode here is a
failure open: an unconfigured check that reads as a passing one, a demo branch that
escapes into production, an email compared case-sensitively against a policy that is
not. Deletion cannot fail that way.

So: change the authentication first, prove it, and only then remove what it replaced.
At no point is the app running without an authentication path — which is the state this
split exists to make impossible.

## Acceptance criteria
- [ ] `current_user` resolves the Access-verified email to an **active** `users` row.
      **Its signature does not change** — frozen since ticket 012, unchanged when 034
      introduced passkeys, unchanged here. The contract test asserting this must still
      pass untouched
- [ ] The assertion is verified **in the API** — signature, issuer, audience — via the
      existing `services/access.py`. The web tier's check stays as well; neither is
      allowed to become the other's excuse
- [ ] Email matching is **case-insensitive and whitespace-trimmed**. Cloudflare returns
      what the identity provider gave it, and an allowlist that misses on `Allen@` versus
      `allen@` fails closed in a way that looks like a bug in Access
- [ ] **Startup refuses** when Access is unconfigured and the deployment is neither demo
      nor explicitly-marked local development — the same shape as ticket 034's refusal to
      start on the default session secret. A per-request check is not enough: a
      deployment with no authentication must not accept a first request
- [ ] `demo_mode` branches to a **fixed demo identity** and requires no assertion. This
      is currently an accident — the demo's `credentials` table is empty, so
      `_bootstrap_user` serves everyone the seeded user — and that accident dies with
      the bootstrap window. It must become deliberate before it stops working
- [ ] Local development gets an explicit identity setting that is **inert unless the
      development marker is set**, and the marker is never set in `fly.web.toml` or
      `fly.api.toml`
- [ ] Passkey login still works. It is not the authentication any more, but it is not
      removed until 047b and must not be left half-wired
- [ ] Tests: an assertion for an email not in `users`; for an inactive user; a missing
      assertion; an assertion failing verification; the demo branch serving its identity
      with no assertion; the startup guard refusing an unconfigured non-demo config; and
      case/whitespace variants of a known email all resolving to the same row

## Files
- `api/app/deps.py`
- `api/app/services/access.py`
- `api/app/config.py`
- `api/tests/test_deps_access_auth.py`

## Notes

**Failing closed is not the same as being correct.** The team-domain incident in ADR 0002
refused *everyone*, owner included, and looked from the outside exactly like Access
working. Every refusal added here logs its reason, and no refusal explains itself in the
response body.

**Do not widen `current_user`'s return or signature to carry the email.** Ticket 041
needed the credential id and added a separate `current_identity` rather than touch this;
the same discipline applies. Every route in the app depends on this one.

**`users` stays the allowlist.** Access authenticates; this table authorises. Without it
an over-broad Access policy is a total compromise, which is exactly the property ADR 0007
listed as a condition of the decision.
