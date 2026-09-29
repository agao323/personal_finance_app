# 047a — Make Cloudflare Access the authentication
Status: done
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
- [x] `current_user` resolves the Access-verified email to an **active** `users` row.
      **Its signature does not change** — frozen since ticket 012, unchanged when 034
      introduced passkeys, unchanged here. The contract test asserting this must still
      pass untouched
- [x] The assertion is verified **in the API** — signature, issuer, audience — via the
      existing `services/access.py`. The web tier's check stays as well; neither is
      allowed to become the other's excuse
- [x] Email matching is **case-insensitive and whitespace-trimmed**. Cloudflare returns
      what the identity provider gave it, and an allowlist that misses on `Allen@` versus
      `allen@` fails closed in a way that looks like a bug in Access
- [x] **Startup refuses** when Access is unconfigured and the deployment is neither demo
      nor explicitly-marked local development — the same shape as ticket 034's refusal to
      start on the default session secret. A per-request check is not enough: a
      deployment with no authentication must not accept a first request
- [x] `demo_mode` branches to a **fixed demo identity** and requires no assertion. This
      is currently an accident — the demo's `credentials` table is empty, so
      `_bootstrap_user` serves everyone the seeded user — and that accident dies with
      the bootstrap window. It must become deliberate before it stops working
- [x] Local development gets an explicit identity setting that is **inert unless the
      development marker is set**, and the marker is never set in `fly.web.toml` or
      `fly.api.toml`
- [x] The passkey routes still exist until 047b, but the session cookie they mint is
      **no longer read by `current_user`**. This criterion originally said passkey login
      "still works", which was the wrong instruction: honouring the cookie would be a way
      into the app that never passed Access, which is the bypass this change closes
- [x] Tests: an assertion for an email not in `users`; for an inactive user; a missing
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

## Done — 2026-08-20

`current_user`'s signature is untouched, as it has been since 012. That property has now
survived being implemented three different ways — a stand-in, passkeys, and Access — which
is the strongest argument available for having frozen it.

**Every guard here is doubled, because every failure mode is a fail-open.** `main.lifespan`
refuses to boot a deployment with Access unconfigured; `current_user` refuses every request
in that state regardless. The development identity is inert on an https origin *and* inert
whenever Access is configured. Neither pair is redundant in the way that matters: a check
that lives in one place lives there only until somebody edits that place.

**One acceptance criterion was written wrong and is corrected above.** It asked that passkey
login keep working through this half. Followed literally that would have meant `current_user`
still honouring the session cookie — an authenticated path that never passed Access, which
is precisely the bypass being closed. The passkey ceremonies still complete; what they mint
confers nothing. `test_auth.py` now asserts that a genuine, correctly-signed cookie is worth
exactly as much as a forged one.

**The demo was working by accident.** Its `credentials` table is empty, so the bootstrap
window never closed and every visitor was served the seeded user. Nothing declared that;
it fell out of a mechanism built for a different purpose. It is now an explicit branch with
a test, and it had to land in this half — the accident dies with the bootstrap window, and
noticing that in 047b would have meant noticing it from a broken demo.

**The tests authenticate the way a laptop does**, rather than through a fixture-only
override. Same code path, so a break in development sign-in breaks the suite instead of
passing it.

Three existing tests asserted the old model and were rewritten rather than deleted: a forged
cookie being refused became the stronger claim that no cookie is a way in, and two
bootstrap-window tests went, since the window no longer exists. The temptation with a failing
old test is to preserve it — 042 made that point and it applies here too.

508 passed.
