# 042 — Recover from a rejected Access session without clearing cookies by hand
Status: done
Wave: 5   Lane: —
Blocked by: 036
Read first: docs/runbooks/access-verification.md

## Goal
When the origin refuses a Cloudflare Access assertion, the person holding it should be
able to get back in from the page they are looking at.

## The incident this comes from

Renaming the Access team on 2026-08-19 left every existing browser session carrying a
token whose `iss` was the old team domain. The origin correctly refused it. Recovering
took manual cookie clearing in browser settings, because:

- The app returned a bare `403 Forbidden` with no guidance. *(Fixed — the page now
  explains. That was the stopgap; this ticket is the actual fix.)*
- `https://<app>/cdn-cgi/access/logout` is served by Cloudflare's edge and **could not
  resolve the organisation**, because the org it read from the stale cookie no longer
  existed. It returned "Unable to find your Access organization!"
- The team-domain logout returns 200 but does not touch `CF_Authorization`, which is
  set on the *application's* hostname. So the obvious remedy looked like it worked and
  did nothing.

Every escape hatch was either broken by the same stale value or silently ineffective.

## The idea

**The origin serves the same hostname the cookie is set on, so the origin can delete
it.** `Set-Cookie: CF_Authorization=; Max-Age=0; Path=/` on the 403 response removes
the stale token. The next request carries none, Cloudflare Access issues a fresh one,
and the fresh one has the current issuer.

## Acceptance criteria
- [x] A 403 caused by an assertion that was **present and failed to verify** clears
      `CF_Authorization`
- [x] A 403 caused by **no assertion at all** does not — there is nothing to clear, and
      that case is an ordinary refusal rather than a stuck session
- [x] **No automatic redirect.** The page says the session was cleared and invites a
      reload. Redirecting risks a loop: if the rejection is a *configuration* error
      rather than a stale token, clear → Access → fresh token → rejected → clear
      repeats forever and the browser never stops
- [x] The page distinguishes the two outcomes in plain language: "this should work if
      you reload" versus "if this repeats, the configuration is wrong — check the logs"
- [x] Still says nothing about which check failed or what was expected. That stays in
      the log
- [x] Tests: the cleared-cookie header is present for a failed assertion and absent when
      no assertion was supplied; the response body is unchanged in the second case

## Files
- `web/src/proxy.ts`
- `web/src/lib/access.ts`
- `web/src/proxy.test.ts`

## Notes

**Why this is safe.** Deleting a cookie cannot escalate anything — the worst outcome is
that somebody re-authenticates. It happens only after an assertion has already failed
verification, so it never touches a session the origin considers good.

**Why not just redirect to the Cloudflare logout.** That is what failed during the
incident. It depends on Cloudflare resolving an organisation out of the very cookie
that is broken, so it fails exactly when it is needed.

**The general shape is worth keeping in mind beyond this ticket.** Every recovery path
here read the same corrupted state the failure came from. A recovery mechanism that
shares an input with the thing it recovers from is not a recovery mechanism. This one
deliberately depends on nothing but the browser honouring `Max-Age=0`.

## Done — 2026-08-20

`verifyAccessJwt` now reports whether an assertion was **present and failed** as
distinct from absent, because that difference is the whole ticket: a token that failed
is a stuck session and deleting it is the fix, while no token is an ordinary refusal
with nothing to delete. Handing a `Set-Cookie` to a visitor who never authenticated
would be noise at best.

The page wording branches on the same distinction. "Clear your cookies" is bad advice
for someone who has none — an instruction that does not apply is worse than none, which
is the mistake the stopgap version made.

That stopgap's test had to be updated rather than kept: it asserted the no-assertion
page said "Clear cookies", which was true and is now wrong. Worth noting because the
temptation with a failing old test is to preserve it.

**No redirect, deliberately.** A configuration error would otherwise produce
clear → Access → fresh token → rejected → clear with nothing to stop it. A reload the
reader chooses cannot loop, and the page says what a repeat means so the two causes stay
distinguishable.
