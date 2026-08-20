# 044 — Account recovery from behind Cloudflare Access
Status: done
Wave: 5   Lane: —
Blocked by: 041
Read first: docs/adr/0002-auth.md

## Goal
Recover a locked-out account entirely in the browser, with no script and nothing outside
the website.

## The gap

`docs/SECURITY.md` and ADR 0002 both said "a lost passkey is recovered by re-registering
from behind Access." **Nothing implemented it**, and every route back was closed:

| Route | Result |
|---|---|
| Sign in | No passkey — impossible |
| `/settings/passkeys` | Needs a session, which needs a passkey |
| Another member issues an invitation | 409 — refused for anyone who already has a passkey |
| Another member removes your credential | 404 — cross-user removal is refused |
| Bootstrap window | Shut permanently on the first registration |
| `make seed` clearing credentials | Refuses against a database marked real |

Losing one device meant a permanent lockout recoverable only by direct database access.
The guard against removing your last passkey was built; the door back was not.

## Acceptance criteria
- [x] `/recover` registers a replacement passkey with **no session**, identified only by
      Cloudflare Access
- [x] The **API verifies the assertion itself** — signature, issuer, audience — rather
      than trusting a header the web tier attached
- [x] The `users` table remains the allowlist: an identity Access authenticated but this
      household never added is refused
- [x] **Refused outright when Access is unconfigured**, never allowed without a check
- [x] Existing credentials are left in place
- [x] Reachable from `/login`
- [x] Every refusal returns the same message
- [x] Tests: the unconfigured guard, a missing assertion, an unverifiable one, and that
      recovery needs no session

## Files
- `api/app/services/access.py`
- `api/app/routers/auth.py`
- `web/src/app/recover/page.tsx`
- `web/src/proxy.ts`

## Notes

**This makes Access sufficient to attach a passkey to an account, and that is the point.**
ADR 0002 already named Access as the security and passkeys as the second layer; anything
weaker would not be recoverable by somebody holding no credential, which is the entire
scenario.

**Verified in the API, not inferred from the web tier.** The API has no public address,
but "unreachable" and "unauthenticated" are different properties and only one of them is
enforced by a network. The assertion already reaches the API — the proxy forwards
everything except hop-by-hop headers — so the service that acts on it can check it.

**Unconfigured means refused.** Locally there is nothing in front of the app; an
unguarded version would be a free "register as anybody" endpoint. Absence of a check
must never read as a passing check, and that is the single most important line in
`services/access.py`.

**Old credentials survive recovery.** A phone that turns up in a coat pocket still works,
and deciding what to remove is better done signed in than while panicking.
